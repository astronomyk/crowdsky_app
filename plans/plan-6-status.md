# Screen 6: Stacking Status

## Source
Adapt from `crowdsky_app_2/screens/status_screen.py` to handle both Seestar and local hard-drive stacking.

## Layout (from wireframe)
```
+----------------------------------+
| < Back    "Stacking Progress"    |
+----------------------------------+
| X / Y jobs completed             |
| Estimated time remaining: MM:SS  |
+----------------------------------+
| -- Stacking Jobs --              |
| 1. path/ip : target : chunk : % |
| 2. path/ip : target : chunk : % |
| ...                              |
+----------------------------------+
| -- Upload Jobs --                |
| 1. path/ip : target : chunk : % |
| ...                              |
+----------------------------------+
|    [ Cancel ] (red)              |
|    [ Back to Home ] (on done)    |
+----------------------------------+
```

## What to Copy
- `crowdsky_app_2/screens/status_screen.py` -> `screens/status_screen.py`
- `crowdsky_app_2/services/job_broker.py` -> `services/job_broker.py`
- `crowdsky_app_2/widgets/job_list_item.py` -> `widgets/job_list_item.py`
- KV layout blocks from `crowdsky_app_2/crowdsky.kv`

## Changes from v2

### status_screen.py
1. Back navigation: -> `"home"` instead of `"dashboard"`
2. On enter: check `AppState().job_source` to determine broker mode
3. When `job_source == "harddrive"`: build `LocalStackJob` instances for red blocks
4. On completion: set `AppState().needs_refresh = True`

### job_broker.py — Extend with LocalStackJob

**New dataclass:**
```python
@dataclass
class LocalStackJob:
    """Stacking job that runs on local PC via FrameCollection."""
    id: str
    source_path: str          # Base directory path (replaces seestar IP)
    target: str
    block: dict               # {files: [paths], block_start, exposure, filter, chunk_key}
    status: str = "pending"   # pending -> running -> complete/failed
    progress: float = 0
    output_path: str = ""     # Path to stacked FITS
    thumbnail_path: str = ""  # Path to thumbnail PNG
    chunk_time: str = ""
    error: str = ""
```

**Extended build_queues():**
```python
def build_queues(self, selected_work, traffic_light, job_source, scrub_by_ip=None):
    if job_source == "seestar":
        # Existing v2 logic: StackJob for red, UploadJob for yellow
        ...
    elif job_source == "harddrive":
        for (path, target), data in selected_work_items:
            # Red blocks -> LocalStackJob
            for block in data["red"]:
                self.stack_queue.append(LocalStackJob(
                    id=f"local-{path}-{target}-{block['chunk_key']}",
                    source_path=path,
                    target=target,
                    block=block,
                    chunk_time=block.get("chunk_key", ""),
                ))
            # Yellow files -> UploadJob with source="yellow_local"
            for yellow_file in data["yellow"]:
                self.upload_queue.append(UploadJob(
                    id=f"upload-{yellow_file['chunk_key']}",
                    source="yellow_local",
                    local_path=yellow_file["path"],
                    chunk_key=yellow_file["chunk_key"],
                    target=target,
                    ...
                ))
```

**Extended _stack_dispatcher():**
```python
def _do_stack(self, job):
    if isinstance(job, LocalStackJob):
        # Local stacking via FrameCollection
        from services.local_stacker import stack_local_block
        result = stack_local_block(
            fits_paths=[Path(f) for f in job.block["files"]],
            output_dir=Path(tempfile.mkdtemp()),
        )
        job.output_path = str(result.output_path)
        job.thumbnail_path = str(result.thumbnail_path)
        # Create upload job for the stacked result
        self.upload_queue.append(UploadJob(
            source="stacked_local",
            local_path=str(result.output_path),
            thumbnail_local_path=str(result.thumbnail_path),
            metadata=result,  # StackResult with all metadata
            chunk_key=job.block["chunk_key"],
            target=job.target,
        ))
    elif isinstance(job, StackJob):
        # Existing Seestar batch stack logic (unchanged)
        ...
```

**Extended _do_upload() for local files:**
```python
def _do_upload(self, job):
    if job.source in ("stacked_local", "yellow_local"):
        # Read file from local disk (no Seestar download needed)
        fits_data = open(job.local_path, 'rb').read()
        thumb_data = open(job.thumbnail_local_path, 'rb').read() if job.thumbnail_local_path else None
    else:
        # Existing Seestar download logic
        ...
    # Upload to CrowdSky server via crowdsky_client.upload()
    crowdsky_client.upload_stack(fits_data, thumb_data, metadata)
```

### job_list_item.py — Minor Adapt
- Show `source_path` (directory) instead of IP for HD jobs
- Display format: `dirname : target : chunk_time : status`

## Progress Reporting for Local Stacking
`FrameCollection.process()` doesn't have a built-in progress callback. Workaround:
- Report 0% at start
- Monitor step timing: detect_sources (~20%), align (~50%), stack (~80%), detect_stars (~100%)
- Or simply report 0% -> 100% (binary: running/done)
- Future: could patch FrameCollection to emit progress events

## Interface with Other Screens
- **Receives from Donate screens**:
  - `AppState().selected_work`
  - `AppState().job_source` ("seestar" | "harddrive")
  - `AppState().traffic_light`
  - `AppState().scrub_location_by_ip` (Seestar only)
- **Sends to Home**: `AppState().needs_refresh = True` on completion
- **Back/Done**: navigates to "home"

## Event System (from v2, unchanged pattern)
Broker emits events via callback:
- `stack_start`, `stack_progress`, `stack_complete`, `stack_failed`
- `upload_start`, `upload_complete`, `upload_failed`
- `all_complete`, `cancelled`

StatusScreen listens via `_on_broker_event()`, updates UI on main thread via `Clock.schedule_once()`.

## Verification
- **Seestar flow**: Select targets on Seestar donate -> Status shows stack + upload jobs -> completes
- **HD flow**: Select targets on HD donate -> Status shows local stack + upload jobs -> completes
- Cancel button stops all jobs cleanly
- Progress bar updates for each job
- Estimated time remaining updates
- On completion: "Back to Home" button, needs_refresh set
