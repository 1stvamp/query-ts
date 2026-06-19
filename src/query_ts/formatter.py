from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import StringIO
from typing import Any

import yaml
from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------


class Formatter:
    def format(self, resources: list[dict], resource_type: str) -> str:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------


class JsonFormatter(Formatter):
    def __init__(self, indent: int = 2) -> None:
        self.indent = indent

    def format(self, resources: list[dict], resource_type: str) -> str:
        return json.dumps(resources, indent=self.indent, default=str)


# ---------------------------------------------------------------------------
# YAML
# ---------------------------------------------------------------------------


class YamlFormatter(Formatter):
    def format(self, resources: list[dict], resource_type: str) -> str:
        return yaml.dump(resources, default_flow_style=False, allow_unicode=True).rstrip()


# ---------------------------------------------------------------------------
# Plain text
# ---------------------------------------------------------------------------


_PLAIN_FIELDS: dict[str, list[str]] = {
    "devices": ["hostname", "name"],
    "users": ["loginName", "displayName", "name"],
    "groups": ["name"],
    "services": ["name"],
    "acl": ["name"],
}


class PlainFormatter(Formatter):
    def __init__(self, separator: str = "\n", field: str | None = None) -> None:
        self.separator = separator
        self.field = field

    def _value(self, resource: dict, resource_type: str) -> str:
        if self.field:
            return str(resource.get(self.field, ""))
        for key in _PLAIN_FIELDS.get(resource_type, ["name"]):
            if v := resource.get(key):
                return str(v)
        return str(resource)

    def format(self, resources: list[dict], resource_type: str) -> str:
        return self.separator.join(
            self._value(r, resource_type) for r in resources
        )


# ---------------------------------------------------------------------------
# Rich table
# ---------------------------------------------------------------------------


def _short_ts(ts: str) -> str:
    return ts[:16].replace("T", " ") if ts else ""


# A device counts as online if it holds a live control connection, or was seen
# within this window. The Tailscale API has no plain "online" field, and
# connectedToControl is false for idle-but-reachable nodes (e.g. phones), so
# recency of lastSeen is the practical signal.
DEFAULT_ONLINE_WINDOW_MINUTES = 5


def _is_online(device: dict, window: timedelta) -> bool:
    if device.get("connectedToControl"):
        return True
    last_seen = device.get("lastSeen")
    if not last_seen:
        return False
    try:
        seen = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
    except ValueError:
        return False
    return datetime.now(timezone.utc) - seen < window


def _tag_list(tags: list | None) -> list[str]:
    if not tags:
        return []
    return [t[4:] if t.startswith("tag:") else t for t in tags]


def _strip_domain(user: str) -> str:
    return user.split("@", 1)[0] if "@" in user else user


def _date_only(ts: str) -> str:
    return ts[:10]


def _term_width(fallback: int = 200) -> int:
    return shutil.get_terminal_size((fallback, 24)).columns


# Aliases so --show accepts intuitive names in addition to the canonical keys.
_SHOW_ALIASES: dict[str, str] = {
    "addresses": "ip",
    "address": "ip",
    "ips": "ip",
    "ip-addresses": "ip",
    "status": "online",
    "state": "online",
    "lastseen": "last-seen",
    "seen": "last-seen",
    "displayname": "display",
    "loginname": "login",
    "group": "name",
}


def _norm_show(tokens) -> set[str]:
    out: set[str] = set()
    for tok in tokens or ():
        key = tok.strip().lower().replace("_", "-").replace(" ", "-")
        if not key:
            continue
        out.add(_SHOW_ALIASES.get(key, key))
    return out


@dataclass
class _Col:
    """A responsive table column.

    ``get`` returns the raw cell value: a ``str``/``Text`` for scalar columns
    or a ``list[str]`` when ``is_list`` is set.
    """

    key: str
    header: str
    get: Callable[[dict], Any]
    is_list: bool = False
    no_wrap: bool = False
    justify: str = "left"
    style: str | None = None
    droppable: bool = True
    default: bool = True
    shorten: Callable[[Any], Any] | None = None


def _cell(col: _Col, raw: Any, stacked: bool, short: bool) -> Any:
    if col.is_list:
        items = list(raw or [])
        if short:
            if not items:
                return ""
            extra = len(items) - 1
            return f"{items[0]}  +{extra}" if extra else items[0]
        if stacked:
            return "\n".join(items)
        return ", ".join(items)
    if short and col.shorten is not None:
        return col.shorten(raw)
    return raw


class TableFormatter(Formatter):
    def __init__(
        self,
        color: bool = True,
        width: int | None = None,
        show: set[str] | None = None,
        online_window_minutes: int = DEFAULT_ONLINE_WINDOW_MINUTES,
    ) -> None:
        self.color = color
        self.width = width if width is not None else _term_width()
        self.forced = _norm_show(show)
        self.online_window = timedelta(minutes=online_window_minutes)

    def _console(self) -> tuple[Console, StringIO]:
        buf = StringIO()
        console = Console(
            file=buf, highlight=False, no_color=not self.color, width=self.width
        )
        return console, buf

    def format(self, resources: list[dict], resource_type: str) -> str:
        if not resources:
            return "(no results)"
        method = getattr(self, f"_fmt_{resource_type}", self._fmt_generic)
        return method(resources)

    def _render(self, table: Table) -> str:
        console, buf = self._console()
        console.print(table)
        return buf.getvalue().rstrip()

    def _responsive(
        self,
        cols: list[_Col],
        rows: list[dict],
        degrade: list[tuple[str, str]],
    ) -> str:
        """Render a table that adapts to ``self.width``.

        Columns named in ``self.forced`` are always shown and never dropped or
        value-shortened. Other columns degrade through ``degrade`` (an ordered
        list of ``(action, key)`` steps) until the table fits the width: list
        cells stack onto multiple lines, low-priority columns are dropped, and
        scalar values are shortened, in that order of preference.
        """
        by_key = {c.key: c for c in cols}
        modes = {
            c.key: {
                "dropped": not (c.default or c.key in self.forced),
                "stacked": False,
                "short": False,
            }
            for c in cols
        }
        console, buf = self._console()
        # Console.measure clamps to its own width, so measure against an
        # effectively unconstrained console to get the table's natural minimum
        # (the width below which cells start to crop).
        measure_console = Console(width=10_000)

        def build() -> Table:
            table = Table(
                box=box.ROUNDED, show_header=True, header_style="bold cyan"
            )
            active = [c for c in cols if not modes[c.key]["dropped"]]
            for c in active:
                table.add_column(
                    c.header, style=c.style, no_wrap=c.no_wrap, justify=c.justify
                )
            for row in rows:
                table.add_row(
                    *(
                        _cell(
                            c,
                            c.get(row),
                            modes[c.key]["stacked"],
                            modes[c.key]["short"],
                        )
                        for c in active
                    )
                )
            return table

        table = build()
        for action, key in degrade:
            if measure_console.measure(table).minimum <= self.width:
                break
            if action in ("drop", "short") and key in self.forced:
                continue
            mode = modes.get(key)
            col = by_key.get(key)
            if mode is None or col is None:
                continue
            if action == "stack" and col.is_list:
                mode["stacked"] = True
            elif action == "short":
                mode["short"] = True
                mode["stacked"] = False
            elif action == "drop" and col.droppable:
                mode["dropped"] = True
            else:
                continue
            table = build()

        console.print(table)
        return buf.getvalue().rstrip()

    def _fmt_devices(self, devices: list[dict]) -> str:
        cols = [
            _Col(
                "hostname",
                "Hostname",
                lambda d: d.get("hostname") or d.get("name", ""),
                no_wrap=True,
                style="bold green",
                droppable=False,
            ),
            _Col("os", "OS", lambda d: d.get("os", "")),
            _Col("user", "User", lambda d: d.get("user", ""), shorten=_strip_domain),
            _Col(
                "ip",
                "IP Addresses",
                lambda d: list(d.get("addresses") or []),
                is_list=True,
            ),
            _Col(
                "tags",
                "Tags",
                lambda d: _tag_list(d.get("tags")),
                is_list=True,
                droppable=False,
            ),
            _Col(
                "online",
                "Online",
                lambda d: Text("●", style="green")
                if _is_online(d, self.online_window)
                else Text("○", style="red"),
                justify="center",
                droppable=False,
            ),
            _Col(
                "last-seen",
                "Last Seen",
                lambda d: _short_ts(d.get("lastSeen", "")),
                shorten=_date_only,
                default=False,
            ),
        ]
        degrade = [
            ("stack", "ip"),
            ("stack", "tags"),
            ("drop", "os"),
            ("short", "user"),
            ("short", "last-seen"),
            ("drop", "ip"),
            ("short", "tags"),
            ("drop", "user"),
        ]
        return self._responsive(cols, devices, degrade)

    def _fmt_users(self, users: list[dict]) -> str:
        cols = [
            _Col(
                "login",
                "Login",
                lambda u: u.get("loginName", u.get("name", "")),
                no_wrap=True,
                style="bold green",
                droppable=False,
            ),
            _Col("display", "Display Name", lambda u: u.get("displayName", "")),
            _Col("role", "Role", lambda u: u.get("role", ""), droppable=False),
            _Col("status", "Status", lambda u: u.get("status", "")),
            _Col(
                "created",
                "Created",
                lambda u: _short_ts(u.get("created", "")),
                shorten=_date_only,
            ),
        ]
        degrade = [
            ("short", "created"),
            ("drop", "created"),
            ("drop", "display"),
            ("drop", "status"),
        ]
        return self._responsive(cols, users, degrade)

    def _fmt_groups(self, groups: list[dict]) -> str:
        cols = [
            _Col(
                "name",
                "Group",
                lambda g: g.get("name", ""),
                no_wrap=True,
                style="bold green",
                droppable=False,
            ),
            _Col(
                "members",
                "Members",
                lambda g: list(g.get("members") or []),
                is_list=True,
                droppable=False,
            ),
        ]
        degrade = [("stack", "members"), ("short", "members")]
        return self._responsive(cols, groups, degrade)

    def _fmt_services(self, services: list[dict]) -> str:
        cols = [
            _Col(
                "name",
                "Name",
                lambda s: s.get("name", ""),
                no_wrap=True,
                style="bold green",
                droppable=False,
            ),
            _Col(
                "addrs",
                "Addresses",
                lambda s: list(s.get("addrs") or []),
                is_list=True,
            ),
            _Col(
                "ports",
                "Ports",
                lambda s: list(s.get("ports") or []),
                is_list=True,
                droppable=False,
            ),
            _Col(
                "tags",
                "Tags",
                lambda s: _tag_list(s.get("tags")),
                is_list=True,
            ),
            _Col("comment", "Comment", lambda s: s.get("comment", "")),
        ]
        degrade = [
            ("stack", "addrs"),
            ("stack", "ports"),
            ("stack", "tags"),
            ("drop", "comment"),
            ("short", "addrs"),
            ("drop", "tags"),
            ("short", "ports"),
        ]
        return self._responsive(cols, services, degrade)

    def _fmt_acl(self, acl_items: list[dict]) -> str:
        table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
        table.add_column("Key", style="bold green")
        table.add_column("Value")

        for item in acl_items:
            table.add_row(
                str(item.get("name", "")), json.dumps(item.get("value"), default=str)
            )

        return self._render(table)

    def _fmt_generic(self, resources: list[dict]) -> str:
        if not resources:
            return "(no results)"
        keys = list(resources[0].keys())[:6]
        table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
        for k in keys:
            table.add_column(k)
        for r in resources:
            table.add_row(*[str(r.get(k, "")) for k in keys])
        return self._render(table)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

FORMAT_NAMES = ("table", "json", "yaml", "plain")


def make_formatter(
    fmt: str,
    separator: str = "\n",
    field: str | None = None,
    color: bool = True,
    width: int | None = None,
    show: set[str] | None = None,
    online_window_minutes: int = DEFAULT_ONLINE_WINDOW_MINUTES,
) -> Formatter:
    match fmt:
        case "json":
            return JsonFormatter()
        case "yaml":
            return YamlFormatter()
        case "plain":
            return PlainFormatter(separator=separator, field=field)
        case _:
            return TableFormatter(
                color=color,
                width=width,
                show=show,
                online_window_minutes=online_window_minutes,
            )
