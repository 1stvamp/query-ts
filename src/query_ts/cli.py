"""query-ts: CLI for querying the Tailscale API."""

from __future__ import annotations

import os
import sys

import click

from .api import TailscaleAPIError, TailscaleClient
from .formatter import FORMAT_NAMES, make_formatter
from .query import ParseError, filter_resources

RESOURCE_TYPES = ("devices", "users", "groups", "services", "acl")

EPILOG = """
\b
QUERY LANGUAGE
  Patterns are glob-style (fnmatch) and matched against resource names.

\b
  Name patterns:
    web-*            devices whose hostname starts with "web-"
    *.example.com    devices whose FQDN matches

\b
  Tag patterns:
    tag:env-prod     devices tagged env-prod
    env:prod         same (prefix:suffix expands to prefix-suffix)
    env:prod*        glob on the tag suffix

\b
  Logical operators:
    web AND env:prod      both conditions must match (AND is the default)
    web env:prod          same as above (implicit AND)
    web OR env:prod       either condition
    (web OR api) env:prod bracketed precedence

\b
  Negation:
    -web-*               exclude names matching web-*
    -tag:env-prod        exclude tagged resources
    -- -literal-name     use -- to pass a literal dash-prefixed string

\b
EXAMPLES
  query-ts 'web-*'
  query-ts 'env:production -tag:deprecated'
  query-ts --users 'admin*'
  query-ts --json 'web-* OR api-*'
  query-ts --plain --comma 'env:prod'
  query-ts --type=groups
"""


def _validate_format(ctx: click.Context, param: click.Parameter, value: str) -> str:
    if value and value not in FORMAT_NAMES:
        raise click.BadParameter(
            f"must be one of: {', '.join(FORMAT_NAMES)}", ctx=ctx, param=param
        )
    return value


@click.command(
    "query-ts",
    context_settings={"help_option_names": ["-h", "--help"], "max_content_width": 100},
    epilog=EPILOG,
)
@click.argument("query", default="", metavar="[QUERY]")
# --- resource type ---
@click.option(
    "--devices",
    "resource_type",
    flag_value="devices",
    default=True,
    help="Query devices (default).",
)
@click.option(
    "--users",
    "resource_type",
    flag_value="users",
    help="Query users.",
)
@click.option(
    "--services",
    "resource_type",
    flag_value="services",
    help="Query services exposed by devices.",
)
@click.option(
    "--groups",
    "resource_type",
    flag_value="groups",
    help="Query ACL groups.",
)
@click.option(
    "--acl",
    "resource_type",
    flag_value="acl",
    help="Query ACL rules.",
)
@click.option(
    "-t",
    "--type",
    "resource_type_override",
    metavar="TYPE",
    default=None,
    help=f"Resource type: {', '.join(RESOURCE_TYPES)}.",
    type=click.Choice(RESOURCE_TYPES, case_sensitive=False),
)
# --- output format ---
@click.option(
    "-j",
    "--json",
    "fmt",
    flag_value="json",
    help="Output as JSON.",
)
@click.option(
    "-y",
    "--yaml",
    "fmt",
    flag_value="yaml",
    help="Output as YAML.",
)
@click.option(
    "-p",
    "--plain",
    "fmt",
    flag_value="plain",
    help="Output as plain text (newline-separated names).",
)
@click.option(
    "-f",
    "--format",
    "fmt_override",
    metavar="FORMAT",
    default=None,
    callback=_validate_format,
    help=f"Output format: {', '.join(FORMAT_NAMES)}.",
)
# --- plain output options ---
@click.option(
    "-s",
    "--separator",
    default="\n",
    show_default=False,
    metavar="SEP",
    help="Field separator for plain output (default: newline).",
)
@click.option(
    "-c",
    "--comma",
    is_flag=True,
    default=False,
    help="Use comma separator (shorthand for --separator=,).",
)
@click.option(
    "--field",
    default=None,
    metavar="FIELD",
    help="Field to extract in plain output (e.g. name, id).",
)
# --- connection / auth ---
@click.option(
    "-k",
    "--api-key",
    envvar="TAILSCALE_API_KEY",
    default=None,
    metavar="KEY",
    help="Tailscale API key [env: TAILSCALE_API_KEY].",
)
@click.option(
    "-n",
    "--tailnet",
    envvar="TAILSCALE_TAILNET",
    default="-",
    show_default=True,
    metavar="NET",
    help="Tailnet name or '-' for the authenticated user's tailnet [env: TAILSCALE_TAILNET].",
)
# --- display ---
@click.option(
    "--color/--no-color",
    default=None,
    help="Force or disable colour output (auto-detected by default).",
)
@click.version_option(package_name="query-ts", prog_name="query-ts")
def main(
    query: str,
    resource_type: str,
    resource_type_override: str | None,
    fmt: str | None,
    fmt_override: str | None,
    separator: str,
    comma: bool,
    field: str | None,
    api_key: str | None,
    tailnet: str,
    color: bool | None,
) -> None:
    """Query Tailscale resources using a simple filter DSL.

    QUERY is an optional filter expression.  Without it all resources
    of the selected type are listed.
    """
    resource_type = resource_type_override or resource_type
    fmt = fmt_override or fmt or "table"

    if comma:
        separator = ","

    if color is None:
        color = sys.stdout.isatty()

    if not api_key:
        raise click.UsageError(
            "API key required. Set TAILSCALE_API_KEY or use --api-key."
        )

    try:
        with TailscaleClient(api_key=api_key, tailnet=tailnet) as client:
            resources = _fetch(client, resource_type)
    except TailscaleAPIError as exc:
        raise click.ClickException(str(exc)) from exc

    try:
        results = filter_resources(resources, query, resource_type)
    except ParseError as exc:
        raise click.ClickException(f"Query parse error: {exc}") from exc

    formatter = make_formatter(fmt, separator=separator, field=field, color=color)
    output = formatter.format(results, resource_type)
    if output:
        click.echo(output)


def _fetch(client: TailscaleClient, resource_type: str) -> list[dict]:
    match resource_type:
        case "devices":
            return client.get_devices()
        case "users":
            return client.get_users()
        case "groups":
            return client.get_groups()
        case "services":
            return client.get_services()
        case "acl":
            acl = client.get_acl()
            # Flatten ACL dict into a list of key/value items for filtering
            return [{"name": k, "value": v} for k, v in acl.items()]
        case _:
            raise click.UsageError(f"Unknown resource type: {resource_type}")
