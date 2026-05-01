"""GalleryScreen: Thumbnail grid with filters and pagination."""

from kivy.uix.screenmanager import Screen
from kivy.uix.widget import Widget
from kivy.properties import NumericProperty, BooleanProperty, StringProperty

from ..app_state import AppState
from ..widgets.gallery_card import GalleryCard


class GalleryScreen(Screen):
    current_page = NumericProperty(1)
    items_per_page = NumericProperty(9)
    total_pages = NumericProperty(1)
    is_loading = BooleanProperty(False)
    info_text = StringProperty("")

    # Keep sorted stacks list for pagination without re-sorting each time
    _sorted_stacks = []

    def on_enter(self):
        self.ids.filter_bar.build_from_state()
        self.ids.filter_bar.bind(on_filter_changed=self._on_filter_changed)
        self.ids.pagination_bar.bind(on_page_changed=self._on_page_changed)
        self._refresh_gallery()

    def on_leave(self):
        self.ids.filter_bar.unbind(on_filter_changed=self._on_filter_changed)
        self.ids.pagination_bar.unbind(on_page_changed=self._on_page_changed)

    def _refresh_gallery(self):
        """Recompute pages and show current page."""
        state = AppState()
        stacks = state.filtered_stacks or []
        self._sorted_stacks = sorted(
            stacks,
            key=lambda s: s.get("date_obs_start", ""),
            reverse=True,
        )
        n = len(self._sorted_stacks)
        self.total_pages = max(1, -(-n // self.items_per_page))
        self.current_page = min(self.current_page, self.total_pages)
        self.info_text = f"{n} stacks"
        self._show_page()

    def _show_page(self):
        stacks = self._sorted_stacks
        start = (self.current_page - 1) * self.items_per_page
        page_stacks = stacks[start:start + self.items_per_page]

        grid = self.ids.thumbnail_grid
        grid.clear_widgets()

        for s in page_stacks:
            ra = s.get('ra_deg')
            dec = s.get('dec_deg')
            ra_dec = (f"RA {ra:.1f}\u00b0  Dec {dec:+.1f}\u00b0"
                      if ra is not None and dec is not None else "")
            date_str = s.get("date_obs_start", "-") or "-"
            card = GalleryCard(
                stack_id=s["id"],
                object_name=s.get("object_name", "Unknown"),
                ra_dec_text=ra_dec,
                timestamp_text=date_str[:16],
                chunk_key=s.get("chunk_key", ""),
            )
            card.load_thumbnail()
            grid.add_widget(card)

        # Pad empty cells to keep grid layout stable
        for _ in range(self.items_per_page - len(page_stacks)):
            grid.add_widget(Widget())

        self.ids.pagination_bar.update(self.current_page, self.total_pages)

    def _on_filter_changed(self, *args):
        self.current_page = 1
        self._refresh_gallery()

    def _on_page_changed(self, widget, page):
        self.current_page = page
        self._show_page()
        self.ids.pagination_bar.update(self.current_page, self.total_pages)

    def go_back(self):
        self.manager.current = "home"
