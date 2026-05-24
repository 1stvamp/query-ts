# Homebrew packaging

The formula lives in the tap repo
[`1stvamp/homebrew-tap`](https://github.com/1stvamp/homebrew-tap) at
`Formula/query-ts.rb`. Users install with:

```sh
brew install 1stvamp/tap/query-ts
```

This directory only holds the workflow that keeps that formula up to date.

## Setup

Create a fine-grained Personal Access Token with `contents: write` on the tap
repo and add it to this repo as the `HOMEBREW_TAP_TOKEN` secret.

## Releases

`.github/workflows/homebrew.yml` runs on each `v*` tag and updates the formula's
`url` and `sha256` in the tap (via `mislav/bump-homebrew-formula-action`), based
on the GitHub source tarball for the tag.

## Dependency resources

The formula's `resource` blocks are pinned to the versions in `uv.lock`. The
bump workflow does not touch them, so when the runtime dependencies change,
refresh them in the tap:

```sh
brew update-python-resources query-ts
```
