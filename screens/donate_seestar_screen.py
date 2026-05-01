"""DonateSeestarScreen: Discover Seestars, scan targets, select work."""

import threading

from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.checkbox import CheckBox
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.metrics import dp, sp
from kivy.properties import StringProperty, BooleanProperty, NumericProperty

from ..app_state import AppState
from ..services.seestar_service import find_seestars, add_manual_ip
from ..services.target_scanner import scan_all_seestars, get_device_info
from ..services.crowdsky_client import get_server_chunk_keys
from ..widgets.album_row import AlbumRow
from ..widgets.donate_seestar_card import DonateSeestarCard


class DonateSeestarScreen(Screen):
    is_scanning = BooleanProperty(False)
    scan_status = StringProperty("")
    scan_progress = NumericProperty(0)
    scan_progress_max = NumericProperty(1)
    summary_text = StringProperty("")
    can_proceed = BooleanProperty(False)
    selected_seestar_ip = StringProperty("")
    can_crawl = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._album_rows = {}  # {(ip, target): AlbumRow}
        self._scan_results = None
        self._device_info = {}  # {ip: (serial, model)}

    def on_enter(self):
        state = AppState()
        if self._scan_results:
            # Returning from Status screen — show cached results
            pass
        elif state.available_seestars and self._device_info:
            # Seestars already discovered — show radio list
            self._build_seestar_radio_list()

    def do_scan_network(self):
        """Scan for Seestars on the network (IP discovery only)."""
        n = int(self.ids.seestar_count.text)
        self.is_scanning = True
        self.scan_status = "Scanning for Seestars..."
        self.can_crawl = False
        self.selected_seestar_ip = ""
        threading.Thread(
            target=self._scan_network_thread, args=(n,), daemon=True
        ).start()

    def _scan_network_thread(self, n):
        try:
            seestars = find_seestars(n)
            # Fetch device info for each discovered Seestar
            device_info = {}
            seen_ips = set()
            for hostname, ip in seestars.items():
                if ip in seen_ips:
                    continue
                seen_ips.add(ip)
                serial, model = get_device_info(ip)
                device_info[ip] = (serial, model)
            Clock.schedule_once(
                lambda dt: self._on_network_scan_done(seestars, device_info))
        except Exception as e:
            msg = str(e)
            Clock.schedule_once(
                lambda dt: self._on_network_scan_error(msg))

    def _on_network_scan_done(self, seestars, device_info):
        state = AppState()
        state.available_seestars.update(seestars)
        self._device_info.update(device_info)
        n = len(state.available_seestars)
        self.scan_status = f"Found {n} Seestar(s) — select one to crawl"
        self.is_scanning = False

        if n > 0:
            self._build_seestar_radio_list()

    def _on_network_scan_error(self, error):
        self.scan_status = f"Scan error: {error}"
        self.is_scanning = False

    def _build_seestar_radio_list(self):
        """Build radio button list from discovered Seestars."""
        container = self.ids.cards_container
        container.clear_widgets()
        self._scan_results = None
        self._album_rows = {}

        seen_ips = set()
        for hostname, ip in AppState().available_seestars.items():
            if ip in seen_ips:
                continue
            seen_ips.add(ip)

            serial, model = self._device_info.get(ip, ("", ""))

            row = BoxLayout(
                orientation='horizontal',
                size_hint_y=None,
                height=dp(48),
                spacing=dp(8),
                padding=[dp(8), 0],
            )

            cb = CheckBox(
                group='seestar_select',
                size_hint_x=None,
                width=dp(36),
                active=(self.selected_seestar_ip == ip),
            )
            _ip = ip  # capture for closure
            cb.bind(active=lambda inst, val, sip=_ip: self._on_seestar_selected(sip, val))
            row.add_widget(cb)

            label_text = serial if serial else ip
            if model:
                label_text += f"  ({model})"
            label_text += f"  [{ip}]"

            lbl = Label(
                text=label_text,
                font_size=sp(14),
                color=(0.9, 0.9, 0.95, 1),
                halign='left',
                valign='middle',
            )
            lbl.bind(size=lbl.setter('text_size'))
            row.add_widget(lbl)

            container.add_widget(row)

    def _on_seestar_selected(self, ip, active):
        """Called when a Seestar radio button is toggled."""
        if active:
            self.selected_seestar_ip = ip
            self.can_crawl = True

    def do_add_manual(self):
        """Add a manually entered IP."""
        ip = self.ids.manual_ip.text.strip()
        if not ip:
            return
        result = add_manual_ip(ip)
        state = AppState()
        state.available_seestars.update(result)
        self.ids.manual_ip.text = ""
        self.is_scanning = True
        self.scan_status = f"Fetching info for {ip}..."
        threading.Thread(
            target=self._fetch_manual_info_thread, args=(ip,), daemon=True
        ).start()

    def _fetch_manual_info_thread(self, ip):
        """Fetch device info for a manually added IP, then rebuild radio list."""
        serial, model = get_device_info(ip)
        self._device_info[ip] = (serial, model)
        Clock.schedule_once(lambda dt: self._on_manual_info_done(ip))

    def _on_manual_info_done(self, ip):
        self.scan_status = f"Added {ip}"
        self.is_scanning = False
        self._build_seestar_radio_list()

    def do_crawl_files(self):
        """Scan targets/files for the selected Seestar only."""
        if not self.selected_seestar_ip:
            return
        self.is_scanning = True
        self.scan_status = "Scanning targets..."
        self.can_proceed = False
        threading.Thread(
            target=self._target_scan_thread, daemon=True
        ).start()

    def _target_scan_thread(self):
        state = AppState()

        # Use cached server chunk keys if available, merge with upload journal
        server_keys = state.server_chunk_keys
        if not server_keys:
            try:
                server_keys = get_server_chunk_keys()
                state.server_chunk_keys = server_keys
            except Exception:
                server_keys = set()

        # Merge with upload journal for cross-session dedup
        from ..services.upload_journal import get_known_chunks
        known_chunks = get_known_chunks(server_keys or None)

        # Build a single-entry seestars dict for the selected IP
        ip = self.selected_seestar_ip
        hostname = None
        for h, sip in state.available_seestars.items():
            if sip == ip:
                hostname = h
                break
        if not hostname:
            hostname = ip
        filtered_seestars = {hostname: ip}

        # Scan the selected Seestar
        def _on_scan_progress(idx, total, target_name):
            Clock.schedule_once(lambda dt: self._update_scan_progress(
                idx, total, target_name))

        traffic_light = scan_all_seestars(
            filtered_seestars, known_chunks,
            on_progress=_on_scan_progress,
        )
        state.traffic_light = traffic_light

        device_info = self._device_info
        Clock.schedule_once(
            lambda dt: self._on_target_scan_done(traffic_light, device_info))

    def _update_scan_progress(self, idx, total, target_name):
        self.scan_progress = idx
        self.scan_progress_max = max(total, 1)
        self.scan_status = f"Scanning {target_name}... ({idx + 1}/{total})"

    def _on_target_scan_done(self, traffic_light, device_info):
        """Build UI cards from scan results."""
        container = self.ids.cards_container
        container.clear_widgets()
        self._album_rows = {}
        self._scan_results = traffic_light

        # Group by IP
        by_ip = {}
        for (ip, target), status in traffic_light.items():
            by_ip.setdefault(ip, []).append((target, status))

        total_yellow = 0
        total_red = 0

        for ip, targets in by_ip.items():
            serial, model = device_info.get(ip, ("", ""))
            card = DonateSeestarCard()
            card.serial_number = serial
            card.ip_address = ip
            card.product_model = model

            for target_name, status in sorted(targets, key=lambda t: t[0]):
                green = len(status["green"])
                yellow = len(status["yellow"])
                red = len(status["red"])
                total_yellow += yellow
                total_red += red

                row = AlbumRow()
                row.target_name = target_name
                row.green_count = green
                row.yellow_count = yellow
                row.red_count = red
                row.is_complete = (yellow == 0 and red == 0)
                row.is_selected = not row.is_complete

                self._album_rows[(ip, target_name)] = row
                card.ids.album_list.add_widget(row)

            container.add_widget(card)

        n_seestars = len(by_ip)
        n_targets = sum(len(t) for t in by_ip.values())
        self.summary_text = (
            f"{n_seestars} Seestar(s), {n_targets} target(s), "
            f"{total_yellow} to upload, {total_red} to stack"
        )
        self.can_proceed = (total_yellow + total_red) > 0
        self.is_scanning = False
        self.scan_status = "Scan complete"

    def do_stack_and_upload(self):
        """Collect selections and navigate to Status screen."""
        state = AppState()
        selected = []
        for (ip, target), row in self._album_rows.items():
            if row.is_selected and not row.is_complete:
                selected.append((ip, target))

        if not selected:
            self.scan_status = "Nothing selected"
            return

        # Collect scrub_location per IP from DonateSeestarCards
        scrub_by_ip = {}
        for child in self.ids.cards_container.children:
            if isinstance(child, DonateSeestarCard):
                scrub_by_ip[child.ip_address] = child.scrub_location

        state.selected_work = selected
        state.scrub_location_by_ip = scrub_by_ip
        state.job_source = "seestar"
        self.manager.current = "status"

    def go_back(self):
        self.manager.current = "home"
