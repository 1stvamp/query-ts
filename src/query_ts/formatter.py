from __future__ import annotations

import json
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


def _tag_str(tags: list | None) -> str:
    if not tags:
        return ""
    return ", ".join(t[4:] if t.startswith("tag:") else t for t in tags)


def _short_ts(ts: str) -> str:
    return ts[:16].replace("T", " ") if ts else ""


class TableFormatter(Formatter):
    def __init__(self, color: bool = True) -> None:
        self.color = color

    def _console(self) -> tuple[Console, StringIO]:
        buf = StringIO()
        console = Console(file=buf, highlight=False, no_color=not self.color, width=200)
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

    def _fmt_devices(self, devices: list[dict]) -> str:
        table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
        table.add_column("Hostname", style="bold green", no_wrap=True)
        table.add_column("OS")
        table.add_column("User")
        table.add_column("IP Addresses")
        table.add_column("Tags")
        table.add_column("St", justify="center")
        table.add_column("Last Seen")

        for d in devices:
            name = d.get("hostname") or d.get("name", "")
            os_name = d.get("os", "")
            user = d.get("user", "")
            addrs = ", ".join(d.get("addresses") or [])
            tags = _tag_str(d.get("tags"))
            online = d.get("online", False)
            status = Text("●", style="green") if online else Text("○", style="red")
            last_seen = _short_ts(d.get("lastSeen", ""))
            table.add_row(name, os_name, user, addrs, tags, status, last_seen)

        return self._render(table)

    def _fmt_users(self, users: list[dict]) -> str:
        table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
        table.add_column("Login", style="bold green", no_wrap=True)
        table.add_column("Display Name")
        table.add_column("Role")
        table.add_column("Status")
        table.add_column("Created")

        for u in users:
            login = u.get("loginName", u.get("name", ""))
            display = u.get("displayName", "")
            role = u.get("role", "")
            status = u.get("status", "")
            created = _short_ts(u.get("created", ""))
            table.add_row(login, display, role, status, created)

        return self._render(table)

    def _fmt_groups(self, groups: list[dict]) -> str:
        table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
        table.add_column("Group", style="bold green", no_wrap=True)
        table.add_column("Members")

        for g in groups:
            name = g.get("name", "")
            members = ", ".join(g.get("members") or [])
            table.add_row(name, members)

        return self._render(table)

    def _fmt_services(self, services: list[dict]) -> str:
        table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
        table.add_column("Name", style="bold green", no_wrap=True)
        table.add_column("Addresses")
        table.add_column("Ports")
        table.add_column("Tags")
        table.add_column("Comment")

        for s in services:
            name = s.get("name", "")
            addrs = ", ".join(s.get("addrs") or [])
            ports = ", ".join(s.get("ports") or [])
            tags = _tag_str(s.get("tags"))
            comment = s.get("comment", "")
            table.add_row(name, addrs, ports, tags, comment)

        return self._render(table)

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
) -> Formatter:
    match fmt:
        case "json":
            return JsonFormatter()
        case "yaml":
            return YamlFormatter()
        case "plain":
            return PlainFormatter(separator=separator, field=field)
        case _:
            return TableFormatter(color=color)
