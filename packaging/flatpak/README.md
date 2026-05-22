# Flatpak packaging

The manifest is `io.github._1stvamp.QueryTs.yaml`. The app ID uses `_1stvamp`
(underscore-prefixed) because reverse-DNS components cannot start with a digit.

## Python dependencies

Dependencies are vendored as offline sources in a generated `python3-deps.json`
that sits next to the manifest. Generate it once, and regenerate when the
dependencies change:

```sh
cd packaging/flatpak
flatpak-pip-generator --runtime=org.freedesktop.Sdk//24.08 \
  --output python3-deps hatchling click httpx rich pyyaml
```

## Building locally

```sh
flatpak install flathub org.freedesktop.Platform//24.08 org.freedesktop.Sdk//24.08
flatpak-builder --user --install --force-clean build-dir \
  packaging/flatpak/io.github._1stvamp.QueryTs.yaml
flatpak run io.github._1stvamp.QueryTs --help
```

## CI

`.github/workflows/flatpak.yml` regenerates `python3-deps.json` and builds a
`query-ts.flatpak` bundle on each `v*` tag (and on manual dispatch).

## Flathub note

Flathub is oriented toward graphical apps with AppStream metainfo and a desktop
file. A pure CLI like query-ts may not be accepted there. The manifest and
bundle work for self-hosting or a private remote regardless; if you do pursue
Flathub, add a `.metainfo.xml` file as well.
