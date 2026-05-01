# Screen 2: Sky Map

## Source
New screen extracted from v2 DashboardScreen + enhanced with filters matching web UI (stacks.php map view).

## Layout (from wireframe)
```
+----------------------------------+
| < Back          "Sky Map"        |
+----------------------------------+
| FilterBar: [All|IRCUT|LP] [Obj] [Tel] |
+----------------------------------+
|                                  |
|         Sky Map Widget           |
|    (RA/Dec scatter, zoom, pan)   |
|                                  |
+----------------------------------+
|       Timeline Widget            |
|   (date scatter, zoom, pan)      |
+----------------------------------+
| Selection summary (when active)  |
+----------------------------------+
```

## Key Files to Reference
- `crowdsky_app_2/screens/dashboard_screen.py` — stacks fetching, widget wiring
- `crowdsky_app_2/widgets/sky_map.py` — SkyMapWidget canvas drawing
- `crowdsky_app_2/widgets/timeline.py` — TimelineWidget canvas drawing
- `crowdsky_app_2/widgets/thumbnail_popup.py` — tap-to-preview popup
- `web/stacks.php` lines 502-790 — D3 sky map reference (coloring, grouping, interactions)

## Implementation

### skymap_screen.py
```python
class SkyMapScreen(Screen):
    def on_enter(self):
        state = AppState()
        self._refresh_widgets()
        # Rebuild filter bar options
        self.ids.filter_bar.build_from_state()

    def _refresh_widgets(self):
        state = AppState()
        stacks = state.filtered_stacks or []
        self.ids.sky_map.set_stacks(stacks)
        self.ids.timeline.set_stacks(stacks)

    def _on_filter_changed(self, *args):
        """Called when FilterBar dispatches on_filter_changed."""
        self._refresh_widgets()

    def _on_stack_tap(self, widget, stack_id, chunk_key, object_name):
        """Open ThumbnailPopup on tap."""
        ThumbnailPopup(stack_id=stack_id, object_name=object_name).open()

    def go_back(self):
        self.manager.current = "home"
```

### FilterBar widget (widgets/filter_bar.py) — SHARED with Gallery
Horizontal bar with three filter controls:

1. **Filter Name**: Toggle buttons — "All", "IRCUT" (red dot), "LP" (blue dot)
   - Mutually exclusive single-select
   - Sets `AppState().filter_name_filter`

2. **Object**: Dropdown button showing "All" or "N selected"
   - Tap opens Popup with ScrollView of CheckBoxes + search TextInput
   - "Apply" and "Clear" buttons
   - Sets `AppState().object_filters`

3. **Telescope**: Same dropdown pattern as Object
   - Sets `AppState().telescope_filters`

```python
class FilterBar(BoxLayout):
    __events__ = ('on_filter_changed',)

    def build_from_state(self):
        """Rebuild controls from AppState filter options."""
        state = AppState()
        # Build filter-name toggle buttons
        # Build object dropdown (populate from state.available_objects)
        # Build telescope dropdown (populate from state.available_telescopes)

    def _on_any_filter_change(self):
        AppState().apply_filters()
        self.dispatch('on_filter_changed')

    def on_filter_changed(self, *args):
        pass  # default handler
```

### SkyMapWidget Enhancements (widgets/sky_map.py)
Changes from v2:

1. **Filter-based dot coloring** (matching web UI):
   ```python
   FILTER_COLORS = {
       "IRCUT": (0.97, 0.32, 0.29, 0.8),   # #f85149
       "LP":    (0.35, 0.65, 1.0, 0.8),     # #58a6ff
   }
   DEFAULT_DOT_COLOR = (0.20, 0.60, 1.0, 0.8)  # accent blue
   ```

2. **Group data includes filter_name** for dominant filter in each coordinate group

3. **Dot sizing** matches web: `sqrt_scale` domain [1, max_count], range [4dp, 14dp]

4. **Touch interactions** (already in v2, verify):
   - Pinch-zoom (replaces web's wheel zoom)
   - Two-finger pan (replaces web's right-click drag)
   - Single tap to select/show tooltip
   - Double tap to reset view

### TimelineWidget Enhancements (widgets/timeline.py)
Same filter-based coloring as SkyMapWidget.

### Selection Summary
When spatial or temporal selection is active (brush on sky map or timeline):
- Show "N stacks selected (X.X MB total)" bar at bottom
- "Download All" button (triggers sequential downloads via crowdsky_client)

## Data Flow
1. Home screen pre-fetches stacks -> AppState.server_stacks
2. SkyMapScreen.on_enter() reads AppState.filtered_stacks
3. FilterBar changes -> AppState.apply_filters() -> _refresh_widgets()
4. Filter state persists in AppState, so returning from Gallery preserves filters

## Interface with Other Screens
- **Receives from Home**: server_stacks pre-fetched in AppState
- **Shares with Gallery**: filter state in AppState (bidirectional)
- **Back**: navigates to "home"

## Verification
- Sky map shows dots at correct RA/Dec positions
- Dots colored by filter (red=IRCUT, blue=LP)
- Pinch zoom and pan work
- Tap a dot -> ThumbnailPopup with image
- Filter by IRCUT -> only red dots shown
- Filter by object -> only matching dots shown
- Navigate to Gallery and back -> filters preserved
- Timeline shows date-based scatter with jitter

# Additional thoughts from the Author
- The box containing the sky-map should be square, so that it gives ample room to scroll and zoom with fingers. The remaining screen realestate below it should be filled with the time line
- The sky-map container should be default be zoomed already to fit the Declination axis (-90,+90 deg). This implies that not all of the RA asix will be visible. That's ok. The user can zoom out to see the whole sky or zoom in to focus on a certain arae
- Zooming should be possible with two-finger-pinch movements on both the timeline and sky-map boxes
- Tapping a dot on the timeline should show a pop-up of the thumbnail (as with the web UI)
- Ignore the dot-selection mechanism that is on the web-ui