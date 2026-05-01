"""Queue-based job broker: stack dispatcher + upload dispatcher threads.

Manages the lifecycle of stacking raw frames and uploading results to the
CrowdSky server.  Supports two job sources:

- ``"seestar"``: stacking happens on the Seestar telescope via JSON-RPC
- ``"harddrive"``: stacking happens locally via ``FrameCollection``
"""

import os
import time
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path

from .crowdsky_client import upload

# Minimum total exposure (seconds) for a block to be worth stacking
MIN_EXPTIME = 240

# Temp dir for local stacking output
_TEMP_ROOT = Path(os.path.expanduser("~/.crowdsky/tmp"))


def _get_temp_dir():
    _TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    return _TEMP_ROOT


@dataclass
class StackJob:
    id: str
    source_key: str          # IP for seestar, base_path for harddrive
    target: str
    block: dict
    status: str = "pending"
    progress: float = 0
    output_filename: str = ""
    chunk_time: str = ""
    scrub_location: bool = False
    # Local stacking results (harddrive mode)
    output_path: Path = None
    thumbnail_path: Path = None
    metadata: dict = field(default_factory=dict)


@dataclass
class UploadJob:
    id: str
    source_key: str
    target: str
    filename: str
    chunk_key: str = ""
    source: str = "yellow"    # "yellow" or "stacked"
    status: str = "pending"
    progress: float = 0
    chunk_time: str = ""
    scrub_location: bool = False
    block: dict = field(default_factory=dict)
    # Local file paths (harddrive mode)
    local_fits_path: Path = None
    local_thumb_path: Path = None
    metadata: dict = field(default_factory=dict)


class JobBroker:
    """Manages stack and upload job queues with two dispatcher threads.

    Parameters
    ----------
    on_event : callable
        Callback(event_type: str, data: dict) for UI updates.
        Called from worker threads — caller must schedule to main thread.
    job_source : str
        ``"seestar"`` or ``"harddrive"``.
    """

    def __init__(self, on_event, job_source="seestar"):
        self.job_source = job_source
        self.stack_queue: list[StackJob] = []
        self.upload_queue: list[UploadJob] = []
        self._cancel = threading.Event()
        self._seestar_lock = threading.Lock()
        self._stack_thread = None
        self._upload_thread = None
        self.on_event = on_event
        self._stack_done = threading.Event()
        self._stack_times = []
        self._upload_times = []

    def build_queues(self, selected_work, traffic_light,
                     scrub_by_key=None):
        """Build job queues from donate screen selections.

        Parameters
        ----------
        selected_work : list[tuple]
            List of (source_key, target) tuples.
            source_key is IP for seestar, base_path for harddrive.
        traffic_light : dict
            {(source_key, target): {"green": [...], "yellow": [...], "red": [...]}}
        scrub_by_key : dict, optional
            {source_key: bool} — per-source scrub_location toggle.
        """
        self.stack_queue.clear()
        self.upload_queue.clear()
        scrub_by_key = scrub_by_key or {}

        for key_target in selected_work:
            source_key, target = key_target
            status = traffic_light.get(key_target, {})
            scrub = scrub_by_key.get(source_key, False)

            # Yellow files → upload jobs (already stacked)
            for item in status.get("yellow", []):
                if isinstance(item, tuple):
                    fname, chunk_key = item
                else:
                    fname, chunk_key = item, ""
                job_id = f"upload-{target}-{chunk_key or fname}"
                self.upload_queue.append(UploadJob(
                    id=job_id,
                    source_key=source_key,
                    target=target,
                    filename=fname,
                    chunk_key=chunk_key,
                    source="yellow",
                    scrub_location=scrub,
                    local_fits_path=(Path(fname) if self.job_source == "harddrive"
                                     else None),
                ))

            # Red blocks → stack jobs (raw frames)
            for block in status.get("red", []):
                exposure_seconds = float(block["exposure"].rstrip("s"))
                total_exptime = block["frame_count"] * exposure_seconds
                if total_exptime < MIN_EXPTIME:
                    continue

                block_start = block["block_start"]
                block_end = block["block_end"]
                chunk_time = (f"{block_start.strftime('%H:%M')}-"
                              f"{block_end.strftime('%H:%M')}")
                job_id = (f"stack-{target}-"
                          f"{block_start.strftime('%Y%m%d-%H%M')}")
                self.stack_queue.append(StackJob(
                    id=job_id,
                    source_key=source_key,
                    target=target,
                    block=block,
                    chunk_time=chunk_time,
                    scrub_location=scrub,
                ))

        self._emit("queue_built", {
            "stack_count": len(self.stack_queue),
            "upload_count": len(self.upload_queue),
        })

    def start(self):
        """Spawn stack and upload dispatcher threads."""
        self._cancel.clear()
        self._stack_done.clear()

        self._stack_thread = threading.Thread(
            target=self._stack_dispatcher, daemon=True)
        self._upload_thread = threading.Thread(
            target=self._upload_dispatcher, daemon=True)

        self._stack_thread.start()
        self._upload_thread.start()

        threading.Thread(target=self._monitor, daemon=True).start()

    def cancel(self):
        """Signal both threads to stop after current operation."""
        self._cancel.set()

    @property
    def is_cancelled(self):
        return self._cancel.is_set()

    def estimate_remaining(self):
        """Estimate remaining time in seconds."""
        avg_stack = (sum(self._stack_times) / len(self._stack_times)
                     if self._stack_times else 180)
        avg_upload = (sum(self._upload_times) / len(self._upload_times)
                      if self._upload_times else 30)
        pending_stacks = sum(1 for j in self.stack_queue
                             if j.status in ("pending", "running"))
        pending_uploads = sum(1 for j in self.upload_queue
                              if j.status in ("pending", "running"))
        return pending_stacks * avg_stack + pending_uploads * avg_upload

    def _emit(self, event_type, data=None):
        self.on_event(event_type, data or {})

    def _monitor(self):
        if self._stack_thread:
            self._stack_thread.join()
        if self._upload_thread:
            self._upload_thread.join()

        if self.is_cancelled:
            self._emit("cancelled", {})
            return

        stacked = sum(1 for j in self.stack_queue if j.status == "complete")
        uploaded = sum(1 for j in self.upload_queue if j.status == "complete")
        failed = (sum(1 for j in self.stack_queue if j.status == "failed") +
                  sum(1 for j in self.upload_queue if j.status == "failed"))
        self._emit("all_complete", {
            "stacked": stacked,
            "uploaded": uploaded,
            "failed": failed,
        })

    # ------------------------------------------------------------------
    # Stack dispatcher
    # ------------------------------------------------------------------
    def _stack_dispatcher(self):
        try:
            for job in self.stack_queue:
                if self.is_cancelled:
                    return
                job.status = "running"
                self._emit("stack_start", {
                    "job_id": job.id,
                    "source_key": job.source_key,
                    "target": job.target,
                    "chunk_time": job.chunk_time,
                })

                t0 = time.time()
                try:
                    if self.job_source == "harddrive":
                        self._do_stack_local(job)
                    else:
                        self._do_stack_seestar(job)
                except Exception as e:
                    job.status = "failed"
                    self._emit("stack_failed", {
                        "job_id": job.id,
                        "reason": str(e),
                    })
                else:
                    self._stack_times.append(time.time() - t0)
        finally:
            self._stack_done.set()

    def _do_stack_local(self, job):
        """Stack using FrameCollection on local PC."""
        from .local_stacker import stack_local_block

        block = job.block
        fits_paths = block.get("full_paths", [])
        if not fits_paths:
            raise ValueError("No full_paths in block")

        work_dir = _get_temp_dir() / job.id
        result = stack_local_block(
            fits_paths=fits_paths,
            output_dir=work_dir,
            on_progress=lambda phase, detail: self._emit(
                "stack_progress", {
                    "job_id": job.id,
                    "phase": phase,
                    "detail": detail,
                }
            ),
        )

        job.status = "complete"
        job.progress = 100
        job.output_path = result["fits_path"]
        job.thumbnail_path = result["thumbnail_path"]
        job.metadata = result
        self._emit("stack_complete", {
            "job_id": job.id,
            "output_path": str(result["fits_path"]),
        })

        # Queue upload for the stacked result
        upload_job = UploadJob(
            id=f"upload-{job.target}-stacked-{job.id}",
            source_key=job.source_key,
            target=job.target,
            filename=str(result["fits_path"]),
            source="stacked",
            scrub_location=job.scrub_location,
            local_fits_path=result["fits_path"],
            local_thumb_path=result["thumbnail_path"],
            metadata=result,
            chunk_time=job.chunk_time,
        )
        self.upload_queue.append(upload_job)
        self._emit("upload_queued", {
            "job_id": upload_job.id,
            "target": job.target,
            "chunk_time": job.chunk_time,
        })

    def _do_stack_seestar(self, job):
        """Execute a single stack job on the Seestar."""
        from seestarpy.stack import (
            clear_batch_stack,
            get_batch_stack_status,
            set_batch_stack_setting,
            start_batch_stack,
        )
        from seestarpy.crowdsky.chunks import _rename_output

        block = job.block
        target = job.target

        with self._seestar_lock:
            from .seestar_service import set_active_seestar
            set_active_seestar(job.source_key)
            set_batch_stack_setting(
                f"MyWorks/{target}_sub", block["files"]
            )
            start_batch_stack()

        status = None
        while True:
            if self.is_cancelled:
                try:
                    clear_batch_stack()
                except Exception:
                    pass
                return

            time.sleep(5)
            try:
                status = get_batch_stack_status()
            except Exception:
                continue

            if status is None:
                continue

            state = status.get("state", "")
            if state == "working":
                job.progress = status.get("percent", 0)
                self._emit("stack_progress", {
                    "job_id": job.id,
                    "percent": status.get("percent", 0),
                    "stacked": status.get("stacked_img", 0),
                    "total": status.get("total_img", 0),
                })
            elif state == "complete":
                break
            elif state in ("fail", "cancel"):
                try:
                    clear_batch_stack()
                except Exception:
                    pass
                job.status = "failed"
                self._emit("stack_failed", {
                    "job_id": job.id,
                    "reason": f"Seestar reported: {state}",
                })
                return

        # Rename output
        try:
            new_fit_name = _rename_output(target, block, status)
        except Exception:
            new_fit_name = None

        if not new_fit_name:
            output_file = status.get("output_file", {})
            files = output_file.get("files", [])
            fit_files = [f["name"] for f in files if f["name"].endswith(".fit")]
            new_fit_name = fit_files[0] if fit_files else None

        if not new_fit_name:
            try:
                clear_batch_stack()
            except Exception:
                pass
            job.status = "failed"
            self._emit("stack_failed", {
                "job_id": job.id,
                "reason": "No output file found after stacking",
            })
            return

        try:
            clear_batch_stack()
        except Exception:
            pass

        job.status = "complete"
        job.output_filename = new_fit_name
        job.progress = 100
        self._emit("stack_complete", {
            "job_id": job.id,
            "output_filename": new_fit_name,
        })

        # Create upload job
        upload_job = UploadJob(
            id=f"upload-{target}-stacked-{job.id}",
            source_key=job.source_key,
            target=target,
            filename=new_fit_name,
            source="stacked",
            scrub_location=job.scrub_location,
            block=block,
            chunk_time=job.chunk_time,
        )
        self.upload_queue.append(upload_job)
        self._emit("upload_queued", {
            "job_id": upload_job.id,
            "target": target,
            "chunk_time": job.chunk_time,
        })

    # ------------------------------------------------------------------
    # Upload dispatcher
    # ------------------------------------------------------------------
    def _upload_dispatcher(self):
        idx = 0
        while True:
            if self.is_cancelled:
                return
            if idx < len(self.upload_queue):
                job = self.upload_queue[idx]
                if job.status == "pending":
                    if self.job_source == "harddrive":
                        self._do_upload_local(job)
                    else:
                        self._do_upload_seestar(job)
                idx += 1
            elif self._stack_done.is_set():
                if idx >= len(self.upload_queue):
                    break
            else:
                time.sleep(2)

    def _do_upload_local(self, job):
        """Upload a locally stacked/pre-stacked FITS to CrowdSky."""
        job.status = "running"
        self._emit("upload_start", {
            "job_id": job.id,
            "filename": Path(job.filename).name,
        })

        t0 = time.time()
        try:
            fits_path = job.local_fits_path or Path(job.filename)
            thumb_path = job.local_thumb_path

            upload_kwargs = {"fits_path": str(fits_path)}
            if thumb_path and Path(thumb_path).exists():
                upload_kwargs["thumbnail"] = str(thumb_path)
            if job.metadata:
                upload_kwargs["n_frames_input"] = job.metadata.get("n_frames_input")
                upload_kwargs["n_frames_aligned"] = job.metadata.get("n_frames_aligned")
                upload_kwargs["date_obs_start"] = job.metadata.get("date_obs_start")
                upload_kwargs["date_obs_end"] = job.metadata.get("date_obs_end")
            if job.scrub_location:
                upload_kwargs["scrub_location"] = 1

            result = upload(**upload_kwargs)
            chunk_key = result.get("chunk_key", job.chunk_key)

            # Record in upload journal
            if chunk_key:
                from .upload_journal import record_uploaded_chunk
                record_uploaded_chunk(chunk_key)

            # Move stacked files to persistent cache
            if job.local_fits_path and job.source == "stacked":
                from .stack_cache import move_to_cache
                move_to_cache(
                    fits_path=job.local_fits_path,
                    thumb_path=job.local_thumb_path,
                    target_name=job.target,
                    chunk_key=chunk_key,
                    base_path=job.source_key,
                    metadata=job.metadata,
                )

            job.status = "complete"
            job.progress = 100
            self._emit("upload_complete", {
                "job_id": job.id,
                "chunk_key": chunk_key,
            })
            self._upload_times.append(time.time() - t0)

        except Exception as e:
            job.status = "failed"
            self._emit("upload_failed", {
                "job_id": job.id,
                "reason": str(e),
            })
        finally:
            # Clean up temp dir (files already moved to cache on success)
            if job.local_fits_path and job.source == "stacked":
                work_dir = job.local_fits_path.parent
                if str(work_dir).startswith(str(_TEMP_ROOT)):
                    try:
                        shutil.rmtree(work_dir, ignore_errors=True)
                    except Exception:
                        pass

    def _do_upload_seestar(self, job):
        """Download from Seestar and upload to CrowdSky."""
        job.status = "running"
        self._emit("upload_start", {
            "job_id": job.id,
            "filename": job.filename,
        })

        t0 = time.time()
        fit_stem = job.filename.removesuffix(".fit")
        local_fit = None
        local_thumb = None

        try:
            from .seestar_service import set_active_seestar
            from .file_transfer import download_from_seestar

            with self._seestar_lock:
                local_fit = download_from_seestar(
                    job.target, job.filename, job.source_key
                )
            try:
                with self._seestar_lock:
                    local_thumb = download_from_seestar(
                        job.target, f"{fit_stem}_thn.jpg", job.source_key
                    )
            except Exception:
                local_thumb = None

            upload_kwargs = {"fits_path": local_fit}
            if local_thumb and Path(local_thumb).exists():
                upload_kwargs["thumbnail"] = local_thumb
            if job.block:
                upload_kwargs["n_frames_input"] = job.block.get("frame_count")
                upload_kwargs["date_obs_start"] = (
                    job.block["block_start"].strftime("%Y-%m-%dT%H:%M:%S"))
                upload_kwargs["date_obs_end"] = (
                    job.block["block_end"].strftime("%Y-%m-%dT%H:%M:%S"))
            if job.scrub_location:
                upload_kwargs["scrub_location"] = 1

            result = upload(**upload_kwargs)
            chunk_key = result.get("chunk_key", job.chunk_key)

            job.status = "complete"
            job.progress = 100
            self._emit("upload_complete", {
                "job_id": job.id,
                "chunk_key": chunk_key,
            })
            self._upload_times.append(time.time() - t0)

        except Exception as e:
            job.status = "failed"
            self._emit("upload_failed", {
                "job_id": job.id,
                "reason": str(e),
            })
        finally:
            for f in [local_fit, local_thumb]:
                if f and Path(f).exists():
                    try:
                        Path(f).unlink()
                    except Exception:
                        pass
