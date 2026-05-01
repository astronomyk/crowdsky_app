"""DonateHarddriveScreen: Select directory, crawl for FITS, local stacking."""

import os
import threading

from kivy.clock import Clock
from kivy.uix.screenmanager import Screen
from kivy.properties import BooleanProperty, StringProperty, NumericProperty

from ..app_state import AppState
from ..widgets.album_row import AlbumRow
from ..widgets.donate_harddrive_card import DonateHarddriveCard


class DonateHarddriveScreen(Screen):
    is_crawling = BooleanProperty(False)
    crawl_status = StringProperty("")
    crawl_progress = NumericProperty(0)
    summary_text = StringProperty("")
    can_proceed = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._cards = {}       # {base_path: DonateHarddriveCard}
        self._album_rows = {}  # {(base_path, target): AlbumRow}

    def on_enter(self):
        state = AppState()
        if state.harddrive_base_path:
            self.ids.path_input.text = state.harddrive_base_path
        if state.harddrive_traffic_light:
            self._display_results(state.harddrive_traffic_light)

    def do_browse(self):
        """Open a native folder picker dialog in a background thread."""
        threading.Thread(target=self._browse_worker, daemon=True).start()

    def _browse_worker(self):
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        # Bring the dialog to the front
        root.attributes("-topmost", True)
        folder = filedialog.askdirectory(
            title="Select Seestar data directory",
            initialdir=self.ids.path_input.text or os.path.expanduser("~"),
        )
        root.destroy()

        if folder:
            Clock.schedule_once(lambda dt: self._on_browse_result(folder))

    def _on_browse_result(self, folder):
        self.ids.path_input.text = folder

    def do_crawl(self):
        path = self.ids.path_input.text.strip()
        if not path or not os.path.isdir(path):
            self.crawl_status = "Directory not found"
            return

        state = AppState()
        state.harddrive_base_path = path

        self.is_crawling = True
        self.crawl_status = "Crawling..."
        self.crawl_progress = 0
        threading.Thread(target=self._crawl_worker, daemon=True).start()

    def _crawl_worker(self):
        from ..services.harddrive_crawler import crawl_directory
        from ..services.upload_journal import get_known_chunks

        state = AppState()

        # Ensure server chunk keys are available (fixes race with HomeScreen)
        if not state.server_chunk_keys:
            Clock.schedule_once(
                lambda dt: setattr(self, 'crawl_status', 'Fetching server data...'))
            try:
                from ..services.crowdsky_client import get_server_chunk_keys
                state.server_chunk_keys = get_server_chunk_keys()
            except Exception:
                pass  # Continue with journal fallback

        # Merge server keys with local upload journal
        known_chunks = get_known_chunks(state.server_chunk_keys or None)

        def on_progress(cur, tot, name):
            pct = (cur / max(tot, 1)) * 100
            Clock.schedule_once(
                lambda dt: self._update_progress(pct, name))

        results = crawl_directory(
            state.harddrive_base_path,
            known_chunks,
            on_progress=on_progress,
        )
        state.harddrive_traffic_light = results
        Clock.schedule_once(lambda dt: self._on_crawl_done(results))

    def _update_progress(self, pct, name):
        self.crawl_progress = pct
        self.crawl_status = f"Scanning: {name}"

    def _on_crawl_done(self, results):
        self.is_crawling = False
        self.crawl_progress = 100
        n_targets = len(results)
        self.crawl_status = f"Found {n_targets} target(s)"
        self._display_results(results)

    def _display_results(self, results):
        container = self.ids.cards_container
        container.clear_widgets()
        self._cards.clear()
        self._album_rows.clear()

        # Group by base_path
        by_path = {}
        for (base_path, target), data in results.items():
            by_path.setdefault(base_path, []).append((target, data))

        total_yellow = 0
        total_red = 0

        for base_path, targets in sorted(by_path.items()):
            card = DonateHarddriveCard(dir_path=base_path)
            self._cards[base_path] = card

            for target, data in sorted(targets, key=lambda t: t[0]):
                g = len(data.get("green", []))
                y = len(data.get("yellow", []))
                r = len(data.get("red", []))
                total_yellow += y
                total_red += r

                row = AlbumRow(
                    target_name=target,
                    green_count=g,
                    yellow_count=y,
                    red_count=r,
                    is_selected=(y + r) > 0,
                    is_complete=(y + r) == 0,
                )
                card.ids.album_list.add_widget(row)
                self._album_rows[(base_path, target)] = row

            container.add_widget(card)

        n_targets = sum(1 for r in self._album_rows.values()
                        if r.is_selected and not r.is_complete)
        self.summary_text = (
            f"{n_targets} target(s), "
            f"{total_yellow} to upload, {total_red} to stack"
        )
        self.can_proceed = (total_yellow + total_red) > 0

    def do_stack_and_upload(self):
        state = AppState()
        state.selected_work = [
            key for key, row in self._album_rows.items()
            if row.is_selected and not row.is_complete
        ]
        state.job_source = "harddrive"
        state.traffic_light = state.harddrive_traffic_light

        # Collect scrub toggles per base_path
        state.scrub_location_by_path = {
            base_path: card.scrub_location
            for base_path, card in self._cards.items()
        }

        if state.selected_work:
            self.manager.current = "status"

    def go_back(self):
        self.manager.current = "home"
