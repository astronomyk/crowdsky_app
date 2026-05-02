"""HomeScreen: Central hub with navigation to all app sections."""

import os
import threading

from kivy.clock import Clock
from kivy.uix.screenmanager import Screen
from kivy.properties import BooleanProperty, StringProperty

from ..app_state import AppState
from ..services.credential_store import clear_credentials
from ..services import crowdsky_client


class HomeScreen(Screen):
    is_loading = BooleanProperty(False)
    status_text = StringProperty("")
    is_android = BooleanProperty('ANDROID_ARGUMENT' in os.environ)

    def on_enter(self):
        state = AppState()
        if state.needs_refresh or not state.server_stacks:
            self.is_loading = True
            self.status_text = "Loading stacks..."
            threading.Thread(target=self._fetch_stacks, daemon=True).start()

    def _fetch_stacks(self):
        try:
            stacks = crowdsky_client.get_my_stacks()
            Clock.schedule_once(lambda dt: self._on_stacks_loaded(stacks))
        except Exception as exc:
            msg = str(exc)
            Clock.schedule_once(
                lambda dt: self._on_stacks_error(msg))

    def _on_stacks_loaded(self, stacks):
        state = AppState()
        state.server_stacks = stacks
        state.server_chunk_keys = {
            s["chunk_key"] for s in stacks if s.get("chunk_key")
        }
        state.derive_filter_options()
        state.apply_filters()
        state.needs_refresh = False
        self.is_loading = False
        self.status_text = f"{len(stacks)} stacks loaded"

        # Sync upload journal with server (server is authoritative)
        from ..services.upload_journal import sync_with_server
        sync_with_server(state.server_chunk_keys)

    def _on_stacks_error(self, msg):
        self.is_loading = False
        self.status_text = f"Error: {msg}"

    def go_skymap(self):
        self.manager.current = "skymap"

    def go_gallery(self):
        self.manager.current = "gallery"

    def go_donate_seestar(self):
        self.manager.current = "donate_seestar"

    def go_donate_harddrive(self):
        self.manager.current = "donate_harddrive"

    def go_plan(self):
        self.manager.current = "plan"

    def do_logout(self):
        state = AppState()
        state.clear()
        clear_credentials()
        self.manager.current = "login"
