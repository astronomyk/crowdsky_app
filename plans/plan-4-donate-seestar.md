# Screen 4: Donate From Seestar

## Source
Copy from `crowdsky_app_2/screens/donate_screen.py` with minimal changes.

## Layout (from wireframe)
```
+----------------------------------+
| < Back    "Donate Frames to Science" |
+----------------------------------+
| [How many? ▼]  [Scan Network]   |
| [Manual IP input]  [Add]        |
+----------------------------------+
| Progress bar                     |
+----------------------------------+
| ┌─ seestar.local ─────────────┐ |
| │ [Select All] [Deselect All]  │ |
| │ [Scrub LAT/LONG toggle]     │ |
| │ [x] M 81  G:5 Y:2 R:3      │ |
| │ [x] M 42  G:10 Y:0 R:0     │ |
| │ [ ] NGC 7023  G:0 Y:1 R:5  │ |
| └──────────────────────────────┘ |
| ┌─ seestar-2.local (collapsed)─┐|
| └──────────────────────────────┘ |
+----------------------------------+
|    [ Stack and Upload ]          |
+----------------------------------+
```

## What to Copy
- `crowdsky_app_2/screens/donate_screen.py` -> `screens/donate_seestar_screen.py`
- `crowdsky_app_2/services/seestar_service.py` -> `services/seestar_service.py`
- `crowdsky_app_2/services/target_scanner.py` -> `services/target_scanner.py`
- `crowdsky_app_2/services/file_transfer.py` -> `services/file_transfer.py`
- `crowdsky_app_2/widgets/donate_seestar_card.py` -> `widgets/donate_seestar_card.py`
- `crowdsky_app_2/widgets/album_row.py` -> `widgets/album_row.py`
- `crowdsky_app_2/widgets/seestar_card.py` -> `widgets/seestar_card.py`
- KV layout blocks for all above from `crowdsky_app_2/crowdsky.kv`

## Changes from v2
1. Class rename: `DonateScreen` -> `DonateSeestarScreen`
2. Screen name: `"donate"` -> `"donate_seestar"`
3. Back navigation: `self.manager.current = "dashboard"` -> `self.manager.current = "home"`
4. Before navigating to status, set: `AppState().job_source = "seestar"`
5. Import path updates

## Workflow (unchanged from v2)
1. User selects how many Seestars to find (Spinner 1-5)
2. "Scan Network" discovers Seestars via mDNS broadcast
3. Or "Manual IP" to add directly
4. Radio-button list of discovered Seestars
5. Select one -> "Crawl Files" enabled
6. Crawl scans all targets, classifies as green/yellow/red using traffic_light dict
7. Collapsible DonateSeestarCard per Seestar with AlbumRows
8. Checkboxes for target selection, Select All / Deselect All
9. Scrub LAT/LONG toggle per Seestar
10. "Stack and Upload" collects selections -> AppState -> navigate to Status

## Interface with Other Screens
- **Receives from Home**: AppState.server_chunk_keys (for green classification)
- **Sends to Status**:
  - `AppState().selected_work = [(ip, target), ...]`
  - `AppState().job_source = "seestar"`
  - `AppState().scrub_location_by_ip = {ip: bool, ...}`
  - `AppState().traffic_light = {(ip, target): {...}, ...}`
- **Back**: navigates to "home"

## Verification
- Scan discovers Seestars on local network
- Crawl shows targets with traffic light badges
- Green = already on server, Yellow = pre-stacked on Seestar, Red = raw frames
- Select targets -> "Stack and Upload" navigates to Status with correct data
- Scrub toggle persists per Seestar
