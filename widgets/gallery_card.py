"""GalleryCard: Thumbnail card for the gallery grid."""

import threading
from io import BytesIO

from kivy.clock import Clock
from kivy.core.image import Image as CoreImage
from kivy.uix.boxlayout import BoxLayout
from kivy.properties import (
    NumericProperty, ObjectProperty, StringProperty, BooleanProperty,
)

from ..app_state import AppState
from ..services import crowdsky_client


class GalleryCard(BoxLayout):
    """Single thumbnail card showing stack image and metadata."""

    stack_id = NumericProperty(0)
    thumbnail_texture = ObjectProperty(None, allownone=True)
    object_name = StringProperty("")
    ra_dec_text = StringProperty("")
    timestamp_text = StringProperty("")
    chunk_key = StringProperty("")
    is_loading = BooleanProperty(True)

    def load_thumbnail(self):
        """Async load thumbnail from server, using cache."""
        if not self.stack_id:
            self.is_loading = False
            return

        cached = AppState().thumbnail_cache.get(self.stack_id)
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
        buf = BytesIO(png_bytes)
        img = CoreImage(buf, ext="png")
        self.thumbnail_texture = img.texture
        self.is_loading = False

    def _set_error(self):
        self.is_loading = False

    def on_touch_up(self, touch):
        if self.collide_point(*touch.pos) and self.stack_id:
            from .thumbnail_popup import ThumbnailPopup
            ThumbnailPopup(
                stack_id=self.stack_id,
                object_name=self.object_name,
                chunk_key=self.chunk_key,
            ).open()
            return True
        return super().on_touch_up(touch)
