# PyPI packaging

query-ts is a hatchling-built package. Releases are published to PyPI by
`.github/workflows/release.yml` when a `v*` tag is pushed, using
[trusted publishing](https://docs.pypi.org/trusted-publishers/) (OIDC), so there
is no API token to store.

## One-time setup on pypi.org

1. Create the project (or reserve the name with a first manual upload if needed).
2. Under the project's *Publishing* settings, add a GitHub Actions trusted
   publisher:
   - Owner: `1stvamp`
   - Repository: `query-ts`
   - Workflow: `release.yml`
   - Environment: `pypi`
3. In the GitHub repo, create an environment named `pypi`
   (Settings > Environments).

## Cutting a release

```sh
# bump version in pyproject.toml, commit, then:
git tag v0.1.0
git push origin v0.1.0
```

The workflow builds the sdist and wheel with `uv build`, publishes to PyPI, and
creates a GitHub Release with the artifacts attached.

## Building locally

```sh
uv build        # writes dist/query_ts-*.tar.gz and *.whl
```
