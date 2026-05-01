# Screen 0: Splash / Login

## Source
Copy from `crowdsky_app_2/screens/login_screen.py` with minimal changes.

## Layout (from wireframe)
- CrowdSky banner/logo at top (centered)
- Login form below (centered):
  - Username TextInput
  - Password TextInput (password=True)
  - "Remember me" CheckBox
  - "Log In" Button
  - Error text label (red, hidden by default)
  - "No account? Sign up" link (opens browser)

## What to Copy
- `crowdsky_app_2/screens/login_screen.py` -> `screens/login_screen.py`
- `crowdsky_app_2/services/credential_store.py` -> `services/credential_store.py`
- `crowdsky_app_2/services/crowdsky_client.py` -> `services/crowdsky_client.py`
- KV layout block for `<LoginScreen>` from `crowdsky_app_2/crowdsky.kv`

## Changes from v2
1. Navigation target: `self.manager.current = "dashboard"` -> `self.manager.current = "home"`
2. Import paths: update from `crowdsky_app_2.services` to `crowdsky_app.services`
3. App name in credential_store: `~/.crowdsky/` directory stays the same (shared between versions)

## Login Flow (unchanged)
1. `on_enter()` loads saved credentials, calls `do_login()` after 0.3s delay
2. `do_login()` spawns background thread -> `crowdsky_client.validate_credentials()`
3. Calls `server.list_stacks()` as a test call
4. On 401 -> show error "Invalid username or password"
5. On success -> `AppState.logged_in = True`, save credentials, navigate to Home

## KV Layout
Copy the LoginScreen KV block from v2's crowdsky.kv. Key constants:
- BG_COLOR: (0.08, 0.08, 0.12, 1)
- CARD_COLOR: (0.14, 0.14, 0.20, 1)
- ACCENT_COLOR: (0.20, 0.60, 1.0, 1)

## Interface with Other Screens
- On success: navigates to "home" screen
- Sets AppState: username, password, logged_in
- Saves credentials to `~/.crowdsky/credentials.json` if "Remember me" checked

## Verification
- Launch app -> login screen shown
- Enter valid credentials -> navigates to Home
- Enter invalid credentials -> error message shown
- Check "Remember me", login, restart -> auto-login works
