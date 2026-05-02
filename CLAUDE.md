# CLAUDE.md — Onboarding for AI Assistants

## What is CrowdSky App?

A Kivy-based desktop and Android client for [CrowdSky](https://crowdsky.univie.ac.at), a cloud stacking service for ZWO Seestar S50 telescope users. The app lets observers:

- Log in to their CrowdSky account from desktop or phone
- Browse their stacks on a sky map and gallery
- Upload raw FITS sub-exposures from a local hard drive or directly from a connected Seestar
- Run a local stacking pipeline (PC version) when offline or for testing

- **Status:** Active development, v0.1.1
- **Author:** Kieran Leschinski (University of Vienna)
- **Backend:** [`astronomyk/CrowdSky`](https://github.com/astronomyk/CrowdSky) (PHP + MariaDB + Python worker on Zeus)

## Architecture

The app is a **client-only** UI. It does not run any server, does not have a database, does not handle WebDAV. All persistence is in the cloud, mediated by three HTTP endpoints on the backend:

| Endpoint | Purpose | Auth |
|---|---|---|
| `GET  /api/my_stacks.php` | List the logged-in user's stacks | HTTP Basic |
| `POST /api/upload_stack.php` | Upload a stacked FITS + thumbnail | HTTP Basic |
| `GET  /api/thumbnail.php?id=N` | Fetch a stack's thumbnail PNG | HTTP Basic |

These endpoints are **wrapped in `seestarpy.crowdsky.server`** — the contract really lives in [seestarpy](https://github.com/astronomyk/seestarpy), not in this repo. If the backend changes a response shape, the matching update lands in seestarpy first, then we bump the seestarpy pin here.

For the "Donate from Seestar" flow, the app additionally talks to a Seestar S50 directly over the local network (JSON-RPC over TCP, SMB for file transfer). All of that lives in `seestarpy.connection` / `seestarpy.data` / `seestarpy.crowdsky.chunks`.

## Repo layout

```
crowdsky_app/                  Repo root — also the Python package root
  __init__.py                  Version definition (__version__ = "0.1.1")
  __main__.py                  Allows `python -m crowdsky_app`
  main.py                      Kivy entry point — registers screens/widgets, starts ScreenManager
  app_state.py                 Singleton AppState (auth, filter state, caches, cancel event)
  crowdsky.kv                  Kivy markup language UI layout (33 KB, all screens + widgets)
  buildozer.spec               Android/Buildozer config (target API 33, arm64-v8a)
  CrowdSky.spec                PyInstaller spec for desktop builds (.exe / .app)
  pyproject.toml               uv-managed deps; sources point at sibling repos for editable installs
  uv.lock                      Resolved dependency tree

  screens/                     One file per screen, each defines a Kivy Screen subclass
    login_screen.py
    home_screen.py             Stack list with filters
    skymap_screen.py           D3-style sky map of stacks
    gallery_screen.py          Thumbnail grid with pagination
    donate_seestar_screen.py   Trigger on-device stacks, upload results
    donate_harddrive_screen.py Walk a local dir for Light_*.fit, stack, upload
    status_screen.py           Job progress + log

  services/                    Business logic, no Kivy imports
    credential_store.py        ~/.crowdsky/credentials.json (desktop) / shared prefs (Android)
    crowdsky_client.py         Thin wrapper around seestarpy.crowdsky.server
    file_transfer.py           Pull files off a Seestar via SMB (uses seestarpy.data)
    harddrive_crawler.py       Find Light_*.fit on a local disk, group by chunk
    job_broker.py              Lifecycle: stack → upload → status callbacks
    local_stacker.py           Wraps crowdsky.stacking.FrameCollection (PC fallback)
    seestar_service.py         JSON-RPC to a Seestar (bypasses higher-level seestarpy abstractions)
    stack_cache.py             Move stacked files to ~/.crowdsky/stacks/ after upload
    target_scanner.py          Traffic-light status (green/yellow/red) per target+chunk
    upload_journal.py          Records uploaded chunk_keys for dedup

  widgets/                     Reusable Kivy widgets (filter_bar, gallery_card, sky_map, timeline, etc.)
  hooks/                       PyInstaller hooks (currently just hook-astropy.py)
  screens_layouts/             PNG mockups (design reference, not bundled)
  plans/                       Per-screen development plans (markdown, dev reference)
  .github/workflows/build-desktop.yml   CI: tag v* → PyInstaller → GitHub Release
```

## Sibling repos expected on disk

For local dev, three repos must sit next to each other:

```
D:\Repos\
  ├── crowdsky_app\      (this repo)
  ├── seestarpy\         Seestar SDK + CrowdSky API client
  └── CrowdSky\          Backend repo; provides the `crowdsky` stacking package
```

`pyproject.toml` declares editable sources for both:

```toml
[tool.uv.sources]
seestarpy = { path = "../seestarpy", editable = true }
crowdsky  = { path = "../CrowdSky/crowdsky", editable = true }
```

So `uv sync` installs them from the sibling working trees. Edit seestarpy → restart the app → changes are live.

## The seestarpy junction

In addition to the editable pip install, **a directory junction at `crowdsky_app/seestarpy` is required for PyInstaller and Buildozer builds**. They both look for source files relative to `main.py`, not on `sys.path`. Create the junction once after cloning (no admin rights needed):

```powershell
# Windows (PowerShell)
New-Item -ItemType Junction -Path seestarpy -Target D:\Repos\seestarpy\src\seestarpy
```

```bash
# Linux/macOS
ln -s ../seestarpy/src/seestarpy seestarpy
```

The junction is gitignored (`/seestarpy` in `.gitignore`). The CI workflow recreates it inside the runner before building.

## The bootstrap puzzle (`main.py` lines 20-35)

`main.py` lives at the repo root and uses absolute imports (`from crowdsky_app.widgets.filter_bar import FilterBar`). For these to resolve, the **parent directory of the repo must be on `sys.path`** so that `crowdsky_app` is importable as a package. Three runtime modes need three different bootstraps:

1. **Desktop, source mode (`python main.py`):** Add `os.path.dirname(_APP_DIR)` to `sys.path`. This makes `D:\Repos\` discoverable, so `crowdsky_app` resolves to the working directory.
2. **PyInstaller bundle:** Files are unpacked under `sys._MEIPASS/crowdsky_app/`. Bootstrap inserts `sys._MEIPASS` on the path.
3. **Android (Buildozer):** Buildozer flattens everything into the app root — there is no `crowdsky_app/` subdirectory. Bootstrap registers a **virtual `ModuleType`** with `__path__` pointing at the app directory, so `from crowdsky_app.X import Y` still works.

If you're adding a new entry point or moving files around, this is the most fragile part of the codebase. Test all three modes after restructuring.

## Build commands

### Run from source

```bash
uv sync                       # one-time: install deps + editable sibling installs
uv run python main.py         # launches Kivy desktop window (390x844, phone-sized)
# or:
uv run python -m crowdsky_app # via __main__.py
```

### Desktop binary (PyInstaller)

```bash
uv run pyinstaller CrowdSky.spec --noconfirm
# Output: dist/CrowdSky-{version}.exe (Windows) or dist/CrowdSky-{version} (macOS)
```

The spec is `--onefile`. It bundles Kivy data files via `collect_data_files('kivy')`, embeds the version into Windows VS_VERSION_INFO, and includes 25+ explicit `hiddenimports` because PyInstaller's static analysis doesn't follow the runtime bootstrap.

### Android APK (Buildozer, in WSL)

```bash
buildozer android debug
# Output: bin/crowdsky-{version}-arm64-v8a-debug.apk
```

`buildozer.spec`'s `requirements =` line is the source of truth for runtime deps **on Android specifically** — not all of `pyproject.toml`'s deps work via python-for-android. Heavy scientific libraries (numpy, opencv, astropy) are NOT in the Android `requirements` because there's no PyPI wheel for ARM that python-for-android can use; the Android version is "lite" and falls back to server-side stacking.

### Releases

```bash
git tag v0.1.2
git push origin v0.1.2
```

Pushes a tag → triggers `.github/workflows/build-desktop.yml` → builds Windows + macOS artifacts → creates a GitHub Release.

## State management

`app_state.py` is a thread-safe **singleton** (`AppState()` always returns the same instance). All screens share it. Hot keys:

- `username`, `password`, `logged_in` — auth state
- `server_stacks`, `server_chunk_keys`, `needs_refresh` — cache of the last `/api/my_stacks.php` response
- `filter_name_filter`, `object_filters`, `telescope_filters`, `filtered_stacks` — current filter state shared across Home/Gallery/SkyMap
- `traffic_light` — `{(seestar_id, target): {"green": [...], "yellow": [...], "red": [...]}}` — per-target dedup status (green = already on server)
- `cancel_event` — `threading.Event` for cooperative cancellation of background workers

After login, `AppState.clear()` resets everything; after a successful upload set `needs_refresh = True` so Home re-fetches.

## Authentication

- User enters username + password on `LoginScreen`
- Validated with `seestarpy.crowdsky.server.set_credentials(...)` + a probe call to `/api/my_stacks.php` (401 = bad creds)
- Stored locally in `~/.crowdsky/credentials.json` on desktop, shared prefs on Android (see `services/credential_store.py`)
- HTTP Basic on every subsequent request — no tokens, no cookies
- "Log out" button calls `AppState.clear()` + deletes the credential file

## Common tasks

- **Add a new screen:** Create `screens/foo_screen.py` with a Kivy `Screen` subclass + `<FooScreen>` rule in `crowdsky.kv`. Register in `main.py` (Factory.register + ScreenManager.add_widget). Add to `CrowdSky.spec` `hiddenimports`. Add nav button somewhere.
- **Add a new service:** Create `services/foo.py`. Pure Python, no Kivy imports. Add to `CrowdSky.spec` `hiddenimports`.
- **Bump version:** Edit `__init__.py` only — `buildozer.spec` reads the version regex from there, and `CrowdSky.spec` parses `__init__.py` directly.
- **Add a Python dependency:** Add to `pyproject.toml` `[project.dependencies]`, run `uv lock`, commit `uv.lock`. For Android, also add to `buildozer.spec` `requirements =` if it's needed at runtime on the phone.
- **Change a backend API call:** Don't edit it here — change it in `seestarpy.crowdsky.server` upstream, then bump the seestarpy version (or just `git pull` the sibling).

## Style and conventions

- **Kivy structure:** Layout in `crowdsky.kv` (declarative), behavior in `screens/*.py` and `widgets/*.py` (imperative). Don't put significant logic in `.kv` — it doesn't get type-checked or grep-friendly.
- **Services don't import Kivy.** They return plain Python data. Screens/widgets handle the UI side.
- **Threading:** Long-running work (uploads, stacking, network I/O) goes on a background thread. Use `Clock.schedule_once(...)` to bounce results back to the UI thread before touching widgets.
- **Cancellation:** Always check `AppState().is_cancelled` in tight loops so the user can bail out.
- **No type checker enforced**, but type hints are encouraged on service boundaries.
- **Imports are absolute** (`from crowdsky_app.services.X import Y`), not relative — needed for the bootstrap puzzle to work on Android.

## Backend contract (frozen interface)

The app encodes assumptions about backend response shapes. If the backend changes any of these, this app breaks (and so does the desktop binary in users' hands — there's no auto-update yet):

- **Chunk key format:** `YYYYMMDD.CC_HPnnnnnn` (UTC date, 15-min block 0-95, HEALPix RING pixel at NSIDE=128). Encoded in `seestarpy.crowdsky.chunks`.
- **FITS header fields read on upload:** `TELESCOP`, `OBJECT`, `RA`, `DEC`, `TOTALEXP`/`EXPTIME`, `FILTER`, `DATE-OBS`, `EQMODE`, `PROGRAM`, `CCD-TEMP`, `SITELONG`, `SITELAT`, `GAIN`, `FOCUSPOS`. Missing fields are fine; the server just records nulls.
- **`/api/my_stacks.php` response:** array of dicts with `id`, `chunk_key`, `object_name`, `telescope_id`, `filter_name`, `date_obs_start/end`, `n_frames_input/aligned`, `total_exptime`, `ra_deg`, `dec_deg`, `file_size_bytes`, `created_at`, plus optional metadata.
- **`/api/upload_stack.php` request:** multipart with `file` (FITS), `thumbnail` (PNG), `n_frames_input/aligned`, `date_obs_start/end`, `scrub_location` (0/1).
- **HTTP Basic Auth** against the backend's `users` table (same creds as the web UI).

## Historical notes

- This app was previously vendored inside the backend repo as `crowdsky_app_3/`. Earlier iterations (`crowdsky_app_1/`, `crowdsky_app_2/`) were abandoned and deleted in 2026-05 along with the extraction.
- The package was renamed `crowdsky_app_3` → `crowdsky_app` during extraction. The `_3` suffix only made sense alongside `_1`/`_2` siblings.
- The `crowdsky/` stacking package (used by `services/local_stacker.py`) lives in the parent CrowdSky repo. We get it via the `[tool.uv.sources]` path. If it ever ships to PyPI, drop the source override and just `pip install crowdsky`.

## Reference

- Backend repo: https://github.com/astronomyk/CrowdSky (PHP frontend, Python worker, schema, API endpoints)
- Production URL: https://crowdsky.univie.ac.at
- seestarpy SDK: https://github.com/astronomyk/seestarpy
- Kivy docs: https://kivy.org/doc/stable/
- Buildozer docs: https://buildozer.readthedocs.io/
- PyInstaller docs: https://pyinstaller.org/en/stable/
