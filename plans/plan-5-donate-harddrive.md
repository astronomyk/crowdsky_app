# Screen 5: Donate From Hard Drive

## Source
New screen. Mirrors the Seestar donate workflow but reads from local filesystem and stacks locally using the worker code.

**Desktop only** — disabled on Android (files too large for mobile processing).

## Layout (from wireframe)
```
+----------------------------------+
| < Back    "Donate Frames to Science" |
+----------------------------------+
| [Select file location]  [Crawl] |
+----------------------------------+
| Progress bar + status label      |
+----------------------------------+
| ┌─ /path/to/seestar-data ──────┐|
| │ [Select All] [Deselect All]  │|
| │ [x] M 81  G:5 Y:2 R:3      │|
| │ [x] M 42  G:10 Y:0 R:0     │|
| │ [ ] NGC 7023  G:0 Y:1 R:5  │|
| └──────────────────────────────┘|
| ┌─ /another/path (collapsed)──┐ |
| └──────────────────────────────┘|
+----------------------------------+
|    [ Stack and Upload ]          |
+----------------------------------+
```

## Key Files to Reference
- `crowdsky_app_2/screens/donate_screen.py` — UI pattern to follow
- `crowdsky_app_2/services/target_scanner.py` — traffic light classification pattern
- `seestarpy/crowdsky/chunks.py` — `_parse_light_filename()`, `_floor_to_block()`, `_CROWDSKY_RE`, `_compute_chunk_key()`
- `worker/stacking_adapter.py` — `stack_files()`, `StackResult` for local stacking
- `worker/thumbnail.py` — `generate_thumbnail()` for creating thumbnails of locally stacked files

## New Services

### harddrive_crawler.py
Walks directories to find Seestar FITS files and classify them.

**Seestar on-disk structure:**
```
user_chosen_root/
├── MyWorks/                      (or directly target folders)
│   ├── M 81/                     (stacked output folder)
│   │   ├── DSO_Stacked_38_M 81_20.0s_20260227_225203.fit
│   │   └── CrowdSky_38_M 81_20.0s_LP_20260227.78_HP049152.fit
│   └── M 81_sub/                 (raw sub-frames)
│       ├── Light_M 81_20.0s_LP_20260227-225203.fit
│       └── ...
```

```python
def crawl_directory(root_path, server_chunk_keys, on_progress=None):
    """Walk root, find *_sub/ dirs with Light_*.fit files, classify.

    Returns:
        dict keyed by (virtual_seestar_path, target_name):
            {
                "green": [chunk_keys already on server],
                "yellow": [CrowdSky_* files ready to upload],
                "red": [blocks of raw frames needing stacking],
            }
    """
```

**Algorithm:**
1. Walk `root_path` recursively
2. Find directories matching `*_sub/` containing `Light_*.fit` files
3. For each `*_sub/` dir:
   a. Identify parent as target dir, target_name from dir name (strip `_sub`)
   b. Parse `Light_*.fit` filenames using `_parse_light_filename()`
   c. Group by 15-min blocks using `_floor_to_block()`
   d. For each block, read RA/Dec from first FITS header (local file read)
   e. Compute `chunk_key` using `_compute_chunk_key(block_start, ra, dec)`
   f. Check sibling dir (target_name without `_sub`) for `CrowdSky_*` files -> yellow
   g. Check `server_chunk_keys` for matching chunk_keys -> green
   h. Remaining blocks -> red
4. Group results by "virtual Seestar" (highest parent containing target dirs)

**Reuse from seestarpy.crowdsky.chunks:**
- `_parse_light_filename(filename)` — parse Light_*.fit names
- `_floor_to_block(dt, 15)` — group by 15-min block
- `_CROWDSKY_RE` — identify pre-stacked CrowdSky files
- `_compute_chunk_key(block_start, ra, dec)` — build chunk key

**Local FITS header reading for RA/Dec:**
```python
def _read_local_fits_ra_dec(fits_path):
    """Read RA/Dec from first 5760 bytes of a local FITS file."""
    with open(fits_path, 'rb') as f:
        header_bytes = f.read(5760).decode('ascii', errors='replace')
    ra = dec = None
    for i in range(0, len(header_bytes), 80):
        card = header_bytes[i:i+80]
        if card.startswith('RA      ='):
            ra = float(card.split('=')[1].split('/')[0].strip())
        elif card.startswith('DEC     ='):
            dec = float(card.split('=')[1].split('/')[0].strip())
        if ra is not None and dec is not None:
            return (ra, dec)
    return (None, None)
```

### local_stacker.py
Wraps `worker/stacking_adapter.py` for local PC stacking.

```python
def stack_local_block(fits_paths, output_dir=None):
    """Stack a list of raw FITS files using FrameCollection.

    Args:
        fits_paths: List of Path objects to raw FITS files
        output_dir: Where to write output (default: tempdir)

    Returns:
        StackResult with output_path, thumbnail_path, and metadata
    """
    # Import from worker code (or copied adapter)
    from worker.stacking_adapter import stack_files, StackResult
    from worker.thumbnail import generate_thumbnail

    output_path = output_dir / "stacked.fits"
    result = stack_files(fits_paths, output_path)

    thumb_path = output_path.with_suffix(".png")
    generate_thumbnail(output_path, thumb_path)
    result.thumbnail_path = thumb_path

    return result
```

**Import strategy:** Copy `worker/stacking_adapter.py` and `worker/thumbnail.py` into `services/local_stacker.py` (adapted imports). This avoids coupling to the worker directory and makes the app self-contained for packaging. The core dependency is `seestarpy.stacking.FrameCollection`.

## Implementation

### donate_harddrive_screen.py
```python
class DonateHarddriveScreen(Screen):
    def select_directory(self):
        """Open file chooser for directory selection."""
        # Use plyer.filechooser.choose_dir() for native dialog
        # Or Kivy FileChooserListView in popup
        # Or let user type/paste path directly

    def do_crawl(self):
        """Background: crawl selected directory for FITS files."""
        path = self.ids.path_input.text
        if not os.path.isdir(path):
            self._show_error("Directory not found")
            return
        state = AppState()
        state.harddrive_base_path = path
        threading.Thread(target=self._crawl_worker, daemon=True).start()

    def _crawl_worker(self):
        from services.harddrive_crawler import crawl_directory
        state = AppState()
        results = crawl_directory(
            state.harddrive_base_path,
            state.server_chunk_keys,
            on_progress=self._update_progress
        )
        state.harddrive_traffic_light = results
        Clock.schedule_once(lambda dt: self._display_results(results))

    def _display_results(self, results):
        container = self.ids.cards_container
        container.clear_widgets()
        # Group by virtual Seestar (top-level path)
        for (path, target), data in results.items():
            # Create DonateHarddriveCard (collapsible, with AlbumRows)
            ...

    def do_stack_and_upload(self):
        state = AppState()
        state.selected_work = self._get_selected_work()
        state.job_source = "harddrive"
        state.traffic_light = state.harddrive_traffic_light
        self.manager.current = "status"
```

### DonateHarddriveCard widget (widgets/donate_harddrive_card.py)
Structurally identical to DonateSeestarCard but:
- Shows directory path instead of hostname/IP/serial
- No "Scrub LAT/LONG" toggle (user owns the local data)
- Reuses AlbumRow as-is for green/yellow/red badges

## Interface with Other Screens
- **Receives from Home**: `AppState.server_chunk_keys` for green classification
- **Sends to Status**:
  - `AppState().selected_work = [(path, target), ...]`
  - `AppState().job_source = "harddrive"`
  - `AppState().traffic_light = {(path, target): {...}, ...}`
- **Back**: navigates to "home"

## Verification
- Enter a valid directory path -> "Crawl" finds targets
- Traffic light classification: green/yellow/red counts correct
- Verify against known Seestar SD card dump
- Select targets -> "Stack and Upload" navigates to Status
- "From Hard Drive" button disabled on Android
