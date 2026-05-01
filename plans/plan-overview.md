# CrowdSky App v3 — Project Overview

## Goal

Recreate the CrowdSky web UI as a native Kivy desktop/mobile app, replacing browser-based upload with Seestar and hard-drive donate workflows, and adding local PC stacking via the existing worker code.

## Project Structure

```
crowdsky_app/
├── __init__.py                         # version = "0.1.0"
├── __main__.py                         # python -m crowdsky_app
├── main.py                             # CrowdSkyApp(App), ScreenManager, Factory.register
├── crowdsky.kv                         # All KV layout rules (single file, v2 pattern)
├── app_state.py                        # AppState singleton (expanded from v2)
│
├── screens/
│   ├── __init__.py
│   ├── login_screen.py                 # [Copy v2] Splash + credential login
│   ├── home_screen.py                  # [New] Hub with 4 navigation buttons
│   ├── skymap_screen.py                # [New] Sky map + timeline + filters
│   ├── gallery_screen.py               # [New] Thumbnail grid + filters + pagination
│   ├── donate_seestar_screen.py        # [Copy v2] Seestar discovery + file selection
│   ├── donate_harddrive_screen.py      # [New] Directory crawl + local stacking selection
│   └── status_screen.py                # [Adapt v2] Dual job types (seestar + local)
│
├── services/
│   ├── __init__.py
│   ├── credential_store.py             # [Copy v2]
│   ├── crowdsky_client.py              # [Copy v2]
│   ├── seestar_service.py              # [Copy v2]
│   ├── file_transfer.py                # [Copy v2]
│   ├── target_scanner.py               # [Copy v2]
│   ├── job_broker.py                   # [Extend v2] Add LocalStackJob type
│   ├── harddrive_crawler.py            # [New] Walk dirs, find FITS, group by target/block
│   └── local_stacker.py                # [New] Wraps worker/stacking_adapter.py
│
└── widgets/
    ├── __init__.py
    ├── sky_map.py                      # [Copy v2] Add filter-based dot coloring
    ├── timeline.py                     # [Copy v2] Add filter-based dot coloring
    ├── thumbnail_popup.py              # [Copy v2]
    ├── album_row.py                    # [Copy v2]
    ├── donate_seestar_card.py          # [Copy v2]
    ├── donate_harddrive_card.py        # [New] Card for HD-discovered Seestar dirs
    ├── stat_card.py                    # [Copy v2]
    ├── seestar_card.py                 # [Copy v2]
    ├── job_list_item.py                # [Adapt v2] Add source_path for HD jobs
    ├── progress_panel.py               # [Copy v2]
    ├── filter_bar.py                   # [New] Shared filter controls (Sky Map + Gallery)
    ├── gallery_card.py                 # [New] Thumbnail card for gallery grid
    └── pagination_bar.py               # [New] Page navigation widget
```

## AppState Singleton (app_state.py)

Expanded from v2 with shared filter state and hard-drive support:

```python
class AppState:
    # --- Auth (from v2) ---
    username: str
    password: str
    logged_in: bool

    # --- Seestar discovery (from v2) ---
    available_seestars: dict              # {hostname: ip}

    # --- Server stacks cache (from v2) ---
    server_stacks: list[dict]             # Full /api/my_stacks.php response
    server_chunk_keys: set[str]           # Derived set for dedup
    needs_refresh: bool

    # --- Shared filter state (NEW) ---
    filter_name_filter: str | None        # None = All, or "IRCUT", "LP"
    object_filters: list[str]             # [] = all, or selected subset
    telescope_filters: list[str]          # [] = all, or selected subset
    filtered_stacks: list[dict]           # Computed after apply_filters()

    # --- Filter options (derived from stacks) ---
    available_objects: list[str]
    available_telescopes: list[str]
    available_filter_names: list[str]

    # --- Thumbnail cache ---
    thumbnail_cache: dict[int, bytes]     # stack_id -> PNG bytes

    # --- Selected work (extended from v2) ---
    selected_work: list[tuple]            # [(ip_or_path, target), ...]
    job_source: str                       # "seestar" or "harddrive"
    scrub_location_by_ip: dict

    # --- Hard drive state (NEW) ---
    harddrive_base_path: str
    harddrive_traffic_light: dict         # Traffic light results from crawler

    # --- Cancellation (from v2) ---
    cancel_event: threading.Event

    def apply_filters(self):
        """Recompute filtered_stacks from server_stacks + active filters."""
        result = self.server_stacks
        if self.filter_name_filter:
            result = [s for s in result if s.get("filter_name") == self.filter_name_filter]
        if self.object_filters:
            result = [s for s in result if s.get("object_name") in self.object_filters]
        if self.telescope_filters:
            result = [s for s in result if s.get("telescope_id") in self.telescope_filters]
        self.filtered_stacks = result

    def derive_filter_options(self):
        """Extract distinct filter names, objects, telescopes from stacks."""
        self.available_filter_names = sorted(set(
            s["filter_name"] for s in self.server_stacks if s.get("filter_name")
        ))
        self.available_objects = sorted(set(
            s["object_name"] for s in self.server_stacks if s.get("object_name")
        ))
        self.available_telescopes = sorted(set(
            s["telescope_id"] for s in self.server_stacks if s.get("telescope_id")
        ))
```

## Navigation Flow

```
Login ──> Home ──> Sky Map       (back to Home)
                ──> Gallery       (back to Home)
                ──> Donate Seestar ──> Status ──> Home
                ──> Donate HD ──────> Status ──> Home
                ──> Logout ──> Login
```

ScreenManager with 7 screens, SlideTransition navigation.

## Data Flow

1. **Login**: Validates credentials via `crowdsky_client.validate_credentials()`
2. **Home**: On enter, fetches stacks if `needs_refresh` via `crowdsky_client.get_my_stacks()` (HTTP Basic Auth to `/api/my_stacks.php`). Populates `server_stacks`, derives filter options
3. **Sky Map / Gallery**: Read `filtered_stacks` from AppState. FilterBar changes trigger `apply_filters()` and re-render
4. **Donate screens**: Build `selected_work` list and set `job_source`, navigate to Status
5. **Status**: Reads `job_source` to build appropriate job queues (StackJob vs LocalStackJob). On completion, sets `needs_refresh = True`
6. **Thumbnails**: Fetched via `crowdsky_client.fetch_thumbnail(stack_id)` (HTTP GET to `/thumbnail.php?id=X`). Cached in `thumbnail_cache`

## Shared Interfaces

### FilterBar -> Screens
- FilterBar dispatches `on_filter_changed` event
- Both Sky Map and Gallery bind to this event and re-read `filtered_stacks`
- Filter state persists in AppState, so navigating between Sky Map and Gallery preserves filters

### Donate Screens -> Status Screen
- Set `AppState().selected_work = [(identifier, target), ...]`
- Set `AppState().job_source = "seestar" | "harddrive"`
- Set `AppState().scrub_location_by_ip` (Seestar only)
- Navigate to "status" screen

### Status Screen -> Home
- On completion, sets `AppState().needs_refresh = True`
- Navigate to "home"

## Key Dependencies

- `seestarpy` — FrameCollection for stacking, chunks module for filename parsing
- `kivy` — UI framework
- `requests` — HTTP client
- For local stacking (desktop only): `astropy`, `numpy`, `opencv-python`, `sep-pjw`, `Pillow`

## Implementation Order

1. Scaffolding + main.py + app_state.py + crowdsky.kv skeleton
2. Screen 0: Login (copy from v2)
3. Screen 1: Home (new, simple)
4. Screen 2: Sky Map with FilterBar (extracted from v2 Dashboard + enhanced)
5. Screen 3: Gallery with shared FilterBar + pagination
6. Screen 4: Donate From Seestar (copy from v2)
7. Screen 5: Donate From Hard Drive (new, with harddrive_crawler + local_stacker)
8. Screen 6: Status (adapt from v2 for dual job types)

## Critical Reference Files

| File | Purpose |
|------|---------|
| `crowdsky_app_2/main.py` | App bootstrap, screen manager, factory registration |
| `crowdsky_app_2/app_state.py` | Singleton state pattern |
| `crowdsky_app_2/crowdsky.kv` | KV layout patterns, color scheme |
| `crowdsky_app_2/screens/login_screen.py` | Login flow to copy |
| `crowdsky_app_2/screens/dashboard_screen.py` | Sky map / stats logic to extract |
| `crowdsky_app_2/screens/donate_screen.py` | Seestar donate flow to copy |
| `crowdsky_app_2/screens/status_screen.py` | Job execution UI to adapt |
| `crowdsky_app_2/services/job_broker.py` | Job queue system to extend |
| `crowdsky_app_2/widgets/sky_map.py` | SkyMapWidget to enhance |
| `crowdsky_app_2/widgets/timeline.py` | TimelineWidget to enhance |
| `worker/stacking_adapter.py` | stack_files(), StackResult for local stacking |
| `worker/thumbnail.py` | generate_thumbnail() for local stacking |
| `seestarpy/crowdsky/chunks.py` | _parse_light_filename, _floor_to_block for HD crawler |
| `web/stacks.php` | Reference implementation of sky map, table, filters |
| `web/api/my_stacks.php` | JSON API for stacks data |
