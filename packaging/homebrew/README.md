# Homebrew packaging

`query-ts.rb` is a `Language::Python::Virtualenv` formula intended for a custom
tap, so users can install with:

```sh
brew install 1stvamp/tap/query-ts
```

## One-time setup

1. Create a repo named `1stvamp/homebrew-tap`.
2. Copy `query-ts.rb` into `Formula/query-ts.rb` in that repo.
3. Create a fine-grained Personal Access Token with `contents: write` on the tap
   repo and add it to the `query-ts` repo as the `HOMEBREW_TAP_TOKEN` secret.

## Releases

`.github/workflows/homebrew.yml` runs on each `v*` tag and updates the formula's
`url` and `sha256` in the tap (via `mislav/bump-homebrew-formula-action`), based
on the GitHub source tarball for the tag. The placeholder `sha256` of all zeros
in this formula is replaced on the first release.

## Dependency resources

The `resource` blocks are pinned to the versions in `uv.lock`. The bump action
does not touch them, so when the runtime dependencies change, refresh them:

```sh
brew update-python-resources query-ts
```
