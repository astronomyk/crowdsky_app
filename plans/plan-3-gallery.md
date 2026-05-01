# Screen 3: Gallery

## Source
New screen mirroring web UI table view (stacks.php) but as a thumbnail grid instead of a table.

## Layout (from wireframe)
```
+----------------------------------+
| < Back          "Gallery"        |
+----------------------------------+
| FilterBar: [All|IRCUT|LP] [Obj] [Tel] |
+----------------------------------+
|                                  |
|  [thumb]  [thumb]  [thumb]       |
|  obj/RA   obj/RA   obj/RA       |
|  date     date     date         |
|  chunk    chunk    chunk        |
|                                  |
|  [thumb]  [thumb]  [thumb]       |
|  ...      ...      ...          |
|                                  |
|  [thumb]  [thumb]  [thumb]       |
|  ...      ...      ...          |
|                                  |
+----------------------------------+
|  < 1 [2] 3 4 ... N >            |
+----------------------------------+
```

## Key Files to Reference
- `web/stacks.php` lines 194-272 — table view columns and data
- `web/thumbnail.php` — how thumbnails are proxied
- `crowdsky_app_2/widgets/thumbnail_popup.py` — async thumbnail loading pattern
- `crowdsky_app_2/services/crowdsky_client.py` — fetch_thumbnail() method

## Implementation

### gallery_screen.py
```python
class GalleryScreen(Screen):
    current_page = NumericProperty(1)
    items_per_page = NumericProperty(9)  # 3x3 grid
    total_pages = NumericProperty(1)

    def on_enter(self):
        state = AppState()
        self.ids.filter_bar.build_from_state()
        self._refresh_gallery()

    def _refresh_gallery(self):
        state = AppState()
        stacks = state.filtered_stacks or []
        # Sort by date descending (matching web: ORDER BY date_obs_start DESC)
        stacks = sorted(stacks, key=lambda s: s.get("date_obs_start", ""), reverse=True)
        self.total_pages = max(1, -(-len(stacks) // self.items_per_page))
        self.current_page = min(self.current_page, self.total_pages)
        self._show_page(stacks)

    def _show_page(self, stacks):
        start = (self.current_page - 1) * self.items_per_page
        page_stacks = stacks[start : start + self.items_per_page]
        grid = self.ids.thumbnail_grid
        grid.clear_widgets()
        for s in page_stacks:
            card = GalleryCard(
                stack_id=s["id"],
                object_name=s.get("object_name", "Unknown"),
                ra_dec_text=f"RA {s.get('ra_deg', 0):.1f}, Dec {s.get('dec_deg', 0):+.1f}",
                timestamp_text=s.get("date_obs_start", "-")[:16],
                chunk_key=s.get("chunk_key", ""),
            )
            card.load_thumbnail()  # async background fetch
            grid.add_widget(card)
        # Pad empty cells to keep grid layout stable
        for _ in range(self.items_per_page - len(page_stacks)):
            grid.add_widget(Widget())
        # Update pagination bar
        self.ids.pagination_bar.update(self.current_page, self.total_pages)

    def _on_filter_changed(self, *args):
        self.current_page = 1
        self._refresh_gallery()

    def _on_page_changed(self, widget, page):
        self.current_page = page
        self._refresh_gallery()

    def go_back(self):
        self.manager.current = "home"
```

### GalleryCard widget (widgets/gallery_card.py)
```python
class GalleryCard(BoxLayout):
    stack_id = NumericProperty(0)
    thumbnail_texture = ObjectProperty(None, allownone=True)
    object_name = StringProperty("")
    ra_dec_text = StringProperty("")
    timestamp_text = StringProperty("")
    chunk_key = StringProperty("")
    is_loading = BooleanProperty(True)

    def load_thumbnail(self):
        """Async load thumbnail from server, using cache."""
        state = AppState()
        cached = state.thumbnail_cache.get(self.stack_id)
        if cached:
            self._set_texture(cached)
            return
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self):
        try:
            png_bytes = crowdsky_client.fetch_thumbnail(self.stack_id)
            AppState().thumbnail_cache[self.stack_id] = png_bytes
            Clock.schedule_once(lambda dt: self._set_texture(png_bytes))
        except Exception:
            Clock.schedule_once(lambda dt: self._set_error())

    def _set_texture(self, png_bytes):
        # Convert PNG bytes to Kivy Texture
        from kivy.core.image import Image as CoreImage
        import io
        buf = io.BytesIO(png_bytes)
        img = CoreImage(buf, ext="png")
        self.thumbnail_texture = img.texture
        self.is_loading = False

    def on_touch_up(self, touch):
        if self.collide_point(*touch.pos) and self.stack_id:
            ThumbnailPopup(stack_id=self.stack_id, object_name=self.object_name).open()
```

KV layout for GalleryCard:
```yaml
<GalleryCard>:
    orientation: 'vertical'
    size_hint_y: None
    height: dp(200)
    padding: dp(4)
    spacing: dp(2)
    canvas.before:
        Color:
            rgba: CARD_COLOR
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(6)]

    # Thumbnail image area
    Image:
        texture: root.thumbnail_texture
        size_hint_y: 1
        allow_stretch: True
        keep_ratio: True

    # Metadata labels (compact)
    Label:
        text: root.object_name
        font_size: sp(12)
        bold: True
        size_hint_y: None
        height: dp(16)
    Label:
        text: root.ra_dec_text
        font_size: sp(10)
        color: DIM_COLOR
        size_hint_y: None
        height: dp(14)
    Label:
        text: root.timestamp_text
        font_size: sp(10)
        color: DIM_COLOR
        size_hint_y: None
        height: dp(14)
```

### PaginationBar widget (widgets/pagination_bar.py)
```python
class PaginationBar(BoxLayout):
    __events__ = ('on_page_changed',)

    def update(self, current, total):
        self.clear_widgets()
        # << < buttons
        # Numbered buttons: show up to 7 pages with ellipsis
        # > >> buttons
        # Highlight current page with accent color

    def on_page_changed(self, page):
        pass
```

## Data Flow
1. Reads `AppState().filtered_stacks` (same data as Sky Map)
2. Sorts by date descending
3. Paginates into pages of 9 items
4. Each GalleryCard async-loads its thumbnail from server
5. Thumbnails cached in `AppState().thumbnail_cache`
6. FilterBar changes trigger re-filter + reset to page 1

## Metadata Shown Per Card (from web table view)
- Thumbnail image
- Object name
- RA / Dec
- Date (date_obs_start, truncated to YYYY-MM-DD HH:MM)
- Chunk key (small, dim text)

Tap card -> full-size ThumbnailPopup (lightbox equivalent)

## Interface with Other Screens
- **Shares with Sky Map**: filter state in AppState (bidirectional)
- **Receives from Home**: server_stacks pre-fetched
- **Back**: navigates to "home"

## Verification
- Gallery shows 3x3 grid of thumbnails
- Thumbnails load asynchronously with placeholder
- Metadata text correct per card
- Pagination: page 2 shows next 9 items
- Filter by object -> only matching cards shown
- Tap card -> ThumbnailPopup with full-size image
- Navigate to Sky Map and back -> filters preserved, thumbnails cached
