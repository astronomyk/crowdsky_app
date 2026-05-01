"""StatusScreen: Live stacking and upload job progress.

Shared by both Donate From Seestar and Donate From Hard Drive flows.
The JobBroker abstracts the stacking backend (Seestar JSON-RPC vs local
FrameCollection); this screen just listens to broker events and updates
JobListItem widgets.
"""

from kivy.clock import Clock
from kivy.uix.screenmanager import Screen
from kivy.properties import BooleanProperty, StringProperty, NumericProperty

from ..app_state import AppState
from ..services.job_broker import JobBroker
from ..widgets.job_list_item import JobListItem


class StatusScreen(Screen):
    is_running = BooleanProperty(False)
    is_finished = BooleanProperty(False)
    jobs_completed = NumericProperty(0)
    jobs_total = NumericProperty(0)
    summary_text = StringProperty("0 / 0 jobs completed")
    estimated_remaining = StringProperty("")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._broker = None
        self._job_items = {}  # {job_id: JobListItem}

    def on_enter(self):
        state = AppState()
        state.reset_cancel()

        if not state.selected_work:
            self.summary_text = "No work selected"
            return

        # Reset UI
        self.is_running = True
        self.is_finished = False
        self.jobs_completed = 0
        self.jobs_total = 0
        self.estimated_remaining = ""
        self._job_items.clear()

        self.ids.stack_jobs_list.clear_widgets()
        self.ids.upload_jobs_list.clear_widgets()

        # Create broker
        self._broker = JobBroker(
            on_event=self._on_broker_event,
            job_source=state.job_source,
        )

        # Determine scrub keys based on source
        if state.job_source == "harddrive":
            scrub_keys = state.scrub_location_by_path
        else:
            scrub_keys = state.scrub_location_by_ip

        self._broker.build_queues(
            state.selected_work,
            state.traffic_light,
            scrub_by_key=scrub_keys,
        )

        # Create JobListItem widgets for pre-queued jobs
        for job in self._broker.stack_queue:
            item = JobListItem(
                job_id=job.id,
                source_label=self._short_source(job.source_key),
                target_name=job.target,
                chunk_time=job.chunk_time,
            )
            self._job_items[job.id] = item
            self.ids.stack_jobs_list.add_widget(item)

        for job in self._broker.upload_queue:
            item = JobListItem(
                job_id=job.id,
                source_label=self._short_source(job.source_key),
                target_name=job.target,
                chunk_time=job.chunk_time,
            )
            self._job_items[job.id] = item
            self.ids.upload_jobs_list.add_widget(item)

        self.jobs_total = (len(self._broker.stack_queue)
                           + len(self._broker.upload_queue))
        self._update_summary()

        # Start processing
        self._broker.start()

    def _short_source(self, source_key):
        """Shorten a source key for display (last path component or IP)."""
        if not source_key:
            return ""
        # If it looks like a path, take the last component
        if "/" in source_key or "\\" in source_key:
            import os
            return os.path.basename(source_key.rstrip("/\\"))
        return source_key

    def _on_broker_event(self, event_type, data):
        """Called from broker worker threads — marshal to main thread."""
        Clock.schedule_once(
            lambda dt: self._handle_event(event_type, data))

    def _handle_event(self, event_type, data):
        job_id = data.get("job_id")
        item = self._job_items.get(job_id) if job_id else None

        if event_type == "stack_start":
            if item:
                item.status = "running"
                item.progress = 0
                item.phase_text = ""

        elif event_type == "stack_progress":
            if item:
                # Seestar mode: {percent, stacked, total}
                if "percent" in data:
                    item.progress = data["percent"]
                    item.phase_text = ""
                # Local mode: {phase, detail}
                elif "phase" in data:
                    item.phase_text = data.get("phase", "")

        elif event_type == "stack_complete":
            if item:
                item.status = "complete"
                item.progress = 100
                item.phase_text = ""
            self.jobs_completed += 1
            self._update_estimate()
            self._update_summary()

        elif event_type == "stack_failed":
            if item:
                item.status = "failed"
                item.phase_text = data.get("reason", "")
            self.jobs_completed += 1
            self._update_summary()

        elif event_type == "upload_queued":
            # Dynamically created upload job (from stack completion)
            new_item = JobListItem(
                job_id=data.get("job_id", ""),
                target_name=data.get("target", ""),
                chunk_time=data.get("chunk_time", ""),
            )
            self._job_items[data["job_id"]] = new_item
            self.ids.upload_jobs_list.add_widget(new_item)
            self.jobs_total += 1
            self._update_summary()

        elif event_type == "upload_start":
            if item:
                item.status = "running"
                item.progress = 0

        elif event_type == "upload_complete":
            if item:
                item.status = "complete"
                item.progress = 100
            self.jobs_completed += 1
            self._update_estimate()
            self._update_summary()

        elif event_type == "upload_failed":
            if item:
                item.status = "failed"
            self.jobs_completed += 1
            self._update_summary()

        elif event_type == "all_complete":
            self.is_running = False
            self.is_finished = True
            stacked = data.get("stacked", 0)
            uploaded = data.get("uploaded", 0)
            failed = data.get("failed", 0)
            parts = []
            if stacked:
                parts.append(f"{stacked} stacked")
            if uploaded:
                parts.append(f"{uploaded} uploaded")
            if failed:
                parts.append(f"{failed} failed")
            self.summary_text = "Done: " + ", ".join(parts) if parts else "Done"
            self.estimated_remaining = ""

        elif event_type == "cancelled":
            self.is_running = False
            self.is_finished = True
            self.summary_text = "Cancelled"
            self.estimated_remaining = ""

    def _update_summary(self):
        if self.is_finished:
            return
        self.summary_text = (
            f"{self.jobs_completed} / {self.jobs_total} jobs completed"
        )

    def _update_estimate(self):
        if not self._broker or self.is_finished:
            self.estimated_remaining = ""
            return
        try:
            secs = self._broker.estimate_remaining()
            if secs < 60:
                self.estimated_remaining = "< 1 min remaining"
            else:
                mins = int(secs / 60)
                self.estimated_remaining = f"~{mins} min remaining"
        except Exception:
            self.estimated_remaining = ""

    def do_cancel(self):
        if self._broker:
            self._broker.cancel()
        self.summary_text = "Cancelling..."

    def go_back(self):
        state = AppState()
        state.needs_refresh = True
        state.selected_work = []
        self.manager.current = "home"
