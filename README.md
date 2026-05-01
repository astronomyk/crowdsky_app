# CrowdSky App

Desktop and Android client for the [CrowdSky](https://crowdsky.univie.ac.at) cloud stacking
service for ZWO Seestar S50 telescope users. Built with [Kivy](https://kivy.org).

The backend (PHP frontend, Python stacking worker, MariaDB, u:cloud storage) lives in the
sibling [CrowdSky](https://github.com/astronomyk/CrowdSky) repository.

## What it does

- Log in to your CrowdSky account from desktop or phone
- Browse your stacks on a sky map and gallery
- Upload raw FITS sub-exposures from a local hard drive or directly from a connected Seestar
- Run a local stacking pipeline as a fallback when offline (PC version)

## Local development

Sibling repos expected next to this one:

```
D:\Repos\
  ├── crowdsky_app\         (this repo)
  ├── seestarpy\            (Seestar SDK + CrowdSky API client)
  └── CrowdSky\             (backend repo; provides the `crowdsky` stacking package)
```

```bash
# Install dependencies (resolves seestarpy + crowdsky from sibling paths)
uv sync

# On Windows, create a junction so PyInstaller and Buildozer can find seestarpy at the app root:
# PowerShell:
#   New-Item -ItemType Junction -Path seestarpy -Target ..\seestarpy\src\seestarpy
# (On Linux/macOS use `ln -s ../seestarpy/src/seestarpy seestarpy`)

# Run the app
uv run python main.py
```

## Build

### Desktop (Windows / macOS)

```bash
uv run pyinstaller CrowdSky.spec --noconfirm
# Output: dist/CrowdSky-{version}.(exe|app)
```

### Android

```bash
# In WSL (Buildozer doesn't run natively on Windows)
buildozer android debug
# Output: bin/crowdsky-*.apk
```

## Releases

Tagging a `v*` ref pushes a desktop build through GitHub Actions and uploads the
artifacts to a GitHub Release.

```bash
git tag v0.1.2
git push origin v0.1.2
```

## License

See LICENSE in the root [CrowdSky](https://github.com/astronomyk/CrowdSky) repo
(this app inherits the same license).
