# Snap packaging

`snap/snapcraft.yaml` uses the `python` plugin on `core24` with strict
confinement and the `network` plug (query-ts makes HTTPS calls to the Tailscale
API). The version is read from `pyproject.toml` at build time.

## Building locally

```sh
snapcraft
sudo snap install ./query-ts_*.snap --dangerous
```

## Publishing to the Snap Store

```sh
snapcraft login
snapcraft register query-ts        # one time, claims the name
snapcraft upload --release=stable ./query-ts_*.snap
```

## CI

`.github/workflows/snap.yml` builds the snap on every `v*` tag (and on manual
dispatch) and uploads it as a workflow artifact. Download it from the run and
`snapcraft upload` it, or wire up store credentials later for automated
publishing.
