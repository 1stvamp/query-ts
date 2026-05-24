# query-ts

A command-line tool for querying the [Tailscale API](https://tailscale.com/api).
List and filter devices, users, groups, services, and ACLs using a small,
glob-friendly query language, and render the results as a table, JSON, YAML, or
plain text.

## Features

- Query **devices** (default), **users**, **groups**, **services**, and **ACLs**.
- A simple filter DSL with glob matching, tag matching, `AND`/`OR`, parentheses,
  and negation.
- Human-friendly coloured tables by default, plus `--json`, `--yaml`, and
  `--plain` output for scripting.
- Authenticates with either a Tailscale **API key** or **OAuth2 client
  credentials** (tokens fetched and cached automatically).

## Installation

Install with Homebrew:

```sh
brew install 1stvamp/tap/query-ts
```

Or with snap:

```sh
sudo snap install query-ts
```

Or from PyPI with your tool of choice:

```sh
pip install query-ts
# or, to install as an isolated tool:
uv tool install query-ts
# or:
pipx install query-ts
```

This installs a `query-ts` command and requires Python 3.11+.

To run from a checkout instead (the project is managed with
[uv](https://docs.astral.sh/uv/)):

```sh
uv run query-ts --help
```

## Authentication

Provide **either** an API key **or** OAuth2 client credentials, not both. One
of the two is required; the CLI exits with an error if no credentials are given.

### API key

```sh
export TAILSCALE_API_KEY="tskey-api-..."
# or pass it inline with -k/--api-key
```

### OAuth2 client credentials

Both the ID and secret are required together:

```sh
export TAILSCALE_OAUTH_CLIENT_ID="..."
export TAILSCALE_OAUTH_CLIENT_SECRET="..."
# or pass --oauth-client-id and --oauth-client-secret
```

An access token is obtained via the `client_credentials` grant and cached for
its lifetime, refreshing automatically before it expires.

### Tailnet

By default the authenticated user's own tailnet (`-`) is used. Override it with
`-n/--tailnet` or the `TAILSCALE_TAILNET` environment variable.

## Usage

```sh
query-ts [QUERY] [OPTIONS]
```

`QUERY` is an optional filter expression. Without it, all resources of the
selected type are listed.

```sh
# All devices, as a table
query-ts

# Devices whose name starts with "web-"
query-ts 'web-*'

# Production-tagged devices that aren't deprecated
query-ts 'env:production -tag:deprecated'

# Users matching a pattern
query-ts --users 'admin*'

# JSON output for two name patterns
query-ts --json 'web-* OR api-*'

# Comma-separated device names (implies plain output)
query-ts --comma 'env:prod'

# List ACL groups
query-ts --type=groups
```

## Query language

Patterns are glob-style ([`fnmatch`](https://docs.python.org/3/library/fnmatch.html))
and matched case-insensitively against resource names.

### Name patterns

| Pattern | Matches |
| --- | --- |
| `web-*` | names starting with `web-` |
| `*.example.com` | FQDNs ending in `.example.com` |

### Tag patterns

A word containing a colon is treated as a tag filter. The `prefix:suffix` form
expands to the tag `prefix-suffix`:

| Pattern | Matches tag |
| --- | --- |
| `tag:env-prod` | `env-prod` |
| `env:prod` | `env-prod` (same as above) |
| `env:prod*` | `env-prod`, `env-production`, etc. (glob on the suffix) |

### Logical operators

| Expression | Meaning |
| --- | --- |
| `web AND env:prod` | both conditions (`AND` is the default) |
| `web env:prod` | implicit `AND` (same as above) |
| `web OR env:prod` | either condition |
| `(web OR api) env:prod` | parentheses for precedence |

`AND` and `OR` are case-insensitive.

### Negation

A leading `-` negates a term:

```sh
query-ts '-web-*'            # exclude names matching web-*
query-ts '-tag:env-prod'     # exclude tagged resources
```

A query that begins with `-` (such as a negation) would otherwise be mistaken
for a command-line option. Use `--` to stop option parsing and pass it as the
query:

```sh
query-ts -- -web-*          # exclude names matching web-*
```

## Options

### Resource type

| Flag | Description |
| --- | --- |
| `--devices` | Query devices (default) |
| `--users` | Query users |
| `--groups` | Query ACL groups |
| `--services` | Query Tailscale Services |
| `--acl` | Query ACL rules |
| `-t, --type TYPE` | Resource type: `devices`, `users`, `groups`, `services`, `acl` |

### Output format

| Flag | Description |
| --- | --- |
| `-j, --json` | Output as JSON |
| `-y, --yaml` | Output as YAML |
| `-p, --plain` | Output as plain text (newline-separated names) |
| `-f, --format FORMAT` | Output format: `table`, `json`, `yaml`, `plain` |

The default format is a coloured `table`.

### Plain-text output

| Flag | Description |
| --- | --- |
| `-s, --separator SEP` | Field separator for plain output (default: newline) |
| `-c, --comma` | Use a comma separator; selects plain output unless a format is set explicitly |
| `--field FIELD` | Field to extract in plain output (e.g. `name`, `id`) |

These options only affect `plain` output. When `--field` is omitted, a default
is chosen per resource type (hostname for devices, login for users).

### Connection & authentication

| Flag | Description |
| --- | --- |
| `-k, --api-key KEY` | Tailscale API key (env: `TAILSCALE_API_KEY`) |
| `--oauth-client-id ID` | OAuth2 client ID (env: `TAILSCALE_OAUTH_CLIENT_ID`) |
| `--oauth-client-secret SECRET` | OAuth2 client secret (env: `TAILSCALE_OAUTH_CLIENT_SECRET`) |
| `-n, --tailnet NET` | Tailnet name, or `-` for the authenticated user's tailnet (env: `TAILSCALE_TAILNET`) |

### Display

| Flag | Description |
| --- | --- |
| `--color / --no-color` | Force or disable colour output (auto-detected by default) |
| `--version` | Show the version and exit |
| `-h, --help` | Show help and exit |

## Development

```sh
# Install dependencies (including dev tools)
uv sync

# Run the test suite
uv run pytest tests/ -v
```

Tests use [`respx`](https://lundberg.github.io/respx/) to mock the Tailscale
HTTP API, so no real credentials or network access are required.

## License

[Apache-2.0](LICENSE)
