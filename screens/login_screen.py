"""LoginScreen: CrowdSky credential entry and validation."""

import threading
import webbrowser

from kivy.clock import Clock
from kivy.uix.screenmanager import Screen
from kivy.properties import StringProperty, BooleanProperty

from ..app_state import AppState
from ..services.credential_store import save_credentials, load_credentials
from ..services.crowdsky_client import validate_credentials


class LoginScreen(Screen):
    error_text = StringProperty("")
    is_loading = BooleanProperty(False)

    def on_enter(self):
        """Auto-login if stored credentials exist."""
        username, password = load_credentials()
        if username and password:
            self.ids.username_input.text = username
            self.ids.password_input.text = password
            self.ids.remember_me.active = True
            Clock.schedule_once(lambda dt: self.do_login(), 0.3)

    def do_login(self):
        username = self.ids.username_input.text.strip()
        password = self.ids.password_input.text.strip()

        if not username or not password:
            self.error_text = "Please enter username and password."
            return

        self.is_loading = True
        self.error_text = ""

        threading.Thread(
            target=self._validate_thread,
            args=(username, password),
            daemon=True,
        ).start()

    def _validate_thread(self, username, password):
        try:
            validate_credentials(username, password)
            Clock.schedule_once(
                lambda dt: self._on_login_success(username, password))
        except RuntimeError as exc:
            msg = ("Invalid username or password."
                   if "401" in str(exc) else str(exc))
            Clock.schedule_once(lambda dt: self._on_login_error(msg))
        except Exception as exc:
            Clock.schedule_once(
                lambda dt: self._on_login_error(f"Connection error: {exc}"))

    def _on_login_success(self, username, password):
        self.is_loading = False
        state = AppState()
        state.username = username
        state.password = password
        state.logged_in = True

        if self.ids.remember_me.active:
            save_credentials(username, password)

        self.manager.current = "home"

    def _on_login_error(self, message):
        self.is_loading = False
        self.error_text = message

    def open_signup(self):
        webbrowser.open("https://crowdsky.univie.ac.at/")
