"""Singleton application state shared across all screens."""

import threading


class AppState:
    """Global mutable state for the CrowdSky app v3.

    Attributes
    ----------
    username, password, logged_in : Auth state (set after login).
    available_seestars : dict
        Mapping of hostname -> IP for discovered Seestars.
    server_stacks : list
        Full response from /api/my_stacks — cached on Home screen.
    server_chunk_keys : set
        Derived set of chunk_keys already on server (for dedup).
    needs_refresh : bool
        True after uploads — Home will re-fetch on next enter.
    filter_name_filter : str or None
        Active filter-name filter (None = All, or "IRCUT", "LP").
    object_filters : list
        Active object name filters (empty = all).
    telescope_filters : list
        Active telescope ID filters (empty = all).
    filtered_stacks : list
        Stacks after applying all active filters.
    available_objects : list
        Distinct object names from server_stacks.
    available_telescopes : list
        Distinct telescope IDs from server_stacks.
    available_filter_names : list
        Distinct filter names from server_stacks.
    thumbnail_cache : dict
        {stack_id: bytes} — cached PNG thumbnail data.
    traffic_light : dict
        {(id, target): {"green": [...], "yellow": [...], "red": [...]}}
    selected_work : list
        [(id, target), ...] selected on Donate, consumed by Status.
    job_source : str
        "seestar" or "harddrive" — determines job type on Status screen.
    scrub_location_by_ip : dict
        {ip: bool} — per-Seestar location scrub toggle.
    harddrive_base_path : str
        User-selected root directory for hard drive crawl.
    harddrive_traffic_light : dict
        Crawl results: {(base_path, target): {"green", "yellow", "red"}}.
    scrub_location_by_path : dict
        {base_path: bool} — per-directory location scrub toggle.
    cancel_event : threading.Event
        Set to signal background workers to stop.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        # Auth
        self.username = ""
        self.password = ""
        self.logged_in = False

        # Seestar discovery
        self.available_seestars = {}

        # Server stacks cache
        self.server_stacks = []
        self.server_chunk_keys = set()
        self.needs_refresh = True

        # Shared filter state
        self.filter_name_filter = None
        self.object_filters = []
        self.telescope_filters = []
        self.filtered_stacks = []

        # Filter options (derived)
        self.available_objects = []
        self.available_telescopes = []
        self.available_filter_names = []

        # Thumbnail cache
        self.thumbnail_cache = {}

        # Work selection
        self.traffic_light = {}
        self.selected_work = []
        self.job_source = "seestar"
        self.scrub_location_by_ip = {}

        # Hard drive
        self.harddrive_base_path = ""
        self.harddrive_traffic_light = {}
        self.scrub_location_by_path = {}

        # Tonight's plan (populated by PlanScreen, consumed by PlanResultScreen)
        self.pending_plan = None
        self.plan_seestar_ip = ""

        # Cancellation
        self.cancel_event = threading.Event()

    def apply_filters(self):
        """Recompute filtered_stacks from server_stacks + active filters."""
        result = self.server_stacks
        if self.filter_name_filter:
            result = [s for s in result
                      if s.get("filter_name") == self.filter_name_filter]
        if self.object_filters:
            result = [s for s in result
                      if s.get("object_name") in self.object_filters]
        if self.telescope_filters:
            result = [s for s in result
                      if s.get("telescope_id") in self.telescope_filters]
        self.filtered_stacks = result

    def derive_filter_options(self):
        """Extract distinct filter names, objects, telescopes from stacks."""
        self.available_filter_names = sorted({
            s["filter_name"] for s in self.server_stacks
            if s.get("filter_name")
        })
        self.available_objects = sorted({
            s["object_name"] for s in self.server_stacks
            if s.get("object_name")
        })
        self.available_telescopes = sorted({
            s["telescope_id"] for s in self.server_stacks
            if s.get("telescope_id")
        })

    def reset_cancel(self):
        self.cancel_event.clear()

    def request_cancel(self):
        self.cancel_event.set()

    @property
    def is_cancelled(self):
        return self.cancel_event.is_set()

    def clear(self):
        """Reset all state (used on logout)."""
        self._init()
