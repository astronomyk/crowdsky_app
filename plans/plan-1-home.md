# Screen 1: Home Screen

## Source
New screen (no v2 equivalent). Replaces the v2 Dashboard as the central hub.

## Layout (from wireframe)
```
+----------------------------------+
|  Header: "CrowdSky" + Logout btn |
+----------------------------------+
|                                  |
|  -- Section: "My Observations" --|
|  (blue accent heading)           |
|                                  |
|  [    Sky Map    ]               |
|  [    Gallery    ]               |
|                                  |
|  -- Section: "Donate to Science"-|
|  (green accent heading)          |
|                                  |
|  [  From Seestar  ]             |
|  [  From Hard Drive ]           |
|  (disabled on Android)           |
+----------------------------------+
```

## Implementation

### home_screen.py
```python
class HomeScreen(Screen):
    def on_enter(self):
        # Pre-fetch stacks data if needed (extracted from v2 DashboardScreen)
        state = AppState()
        if state.needs_refresh or not state.server_stacks:
            threading.Thread(target=self._fetch_stacks, daemon=True).start()

    def _fetch_stacks(self):
        """Background: fetch stacks from server, populate AppState."""
        stacks = crowdsky_client.get_my_stacks()
        state = AppState()
        state.server_stacks = stacks
        state.server_chunk_keys = {s["chunk_key"] for s in stacks if s.get("chunk_key")}
        state.derive_filter_options()
        state.apply_filters()
        state.needs_refresh = False

    def go_skymap(self):
        self.manager.current = "skymap"

    def go_gallery(self):
        self.manager.current = "gallery"

    def go_donate_seestar(self):
        self.manager.current = "donate_seestar"

    def go_donate_harddrive(self):
        self.manager.current = "donate_harddrive"

    def do_logout(self):
        state = AppState()
        state.logged_in = False
        state.username = ""
        state.password = ""
        state.server_stacks = []
        state.thumbnail_cache = {}
        credential_store.clear()
        self.manager.current = "login"
```

### Platform detection for "From Hard Drive" button
```python
import os
is_android = 'ANDROID_ARGUMENT' in os.environ

# In KV or on_enter:
# self.ids.btn_harddrive.disabled = is_android
# self.ids.btn_harddrive.opacity = 0.4 if is_android else 1.0
```

## KV Layout
```yaml
<HomeScreen>:
    BoxLayout:
        orientation: 'vertical'
        padding: dp(20)
        spacing: dp(16)
        canvas.before:
            Color:
                rgba: BG_COLOR
            Rectangle:
                pos: self.pos
                size: self.size

        # Header row
        BoxLayout:
            size_hint_y: None
            height: dp(48)
            Label:
                text: "CrowdSky"
                font_size: sp(22)
                bold: True
                color: ACCENT_COLOR
            Button:
                text: "Logout"
                size_hint_x: None
                width: dp(80)
                on_release: root.do_logout()

        # My Observations section
        Label:
            text: "My Observations"
            # blue accent background
            size_hint_y: None
            height: dp(40)

        Button:
            text: "Sky Map"
            size_hint_y: None
            height: dp(56)
            on_release: root.go_skymap()

        Button:
            text: "Gallery"
            size_hint_y: None
            height: dp(56)
            on_release: root.go_gallery()

        # Donate to Science section
        Label:
            text: "Donate to Science"
            # green accent background
            size_hint_y: None
            height: dp(40)

        Button:
            text: "From Seestar"
            size_hint_y: None
            height: dp(56)
            on_release: root.go_donate_seestar()

        Button:
            id: btn_harddrive
            text: "From Hard Drive"
            size_hint_y: None
            height: dp(56)
            on_release: root.go_donate_harddrive()

        Widget:  # spacer
```

## Interface with Other Screens
- **Receives from Login**: AppState has credentials set, logged_in = True
- **Sends to Sky Map / Gallery**: Pre-fetched stacks data in AppState
- **Sends to Donate screens**: Nothing (they fetch their own data)
- **Receives from Status**: `needs_refresh = True` triggers re-fetch on next enter

## Verification
- After login, Home screen shows with 4 buttons
- "Sky Map" / "Gallery" / "From Seestar" navigate correctly
- "From Hard Drive" disabled on Android
- "Logout" clears state and returns to Login
- Stacks data pre-fetched in background on enter
