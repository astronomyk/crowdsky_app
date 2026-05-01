"""Popup that asynchronously loads and displays a stack thumbnail."""

import threading
from io import BytesIO

from kivy.uix.popup import Popup
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.image import Image as KivyImage
from kivy.core.image import Image as CoreImage
from kivy.clock import Clock

from ..app_state import AppState


class ThumbnailPopup(Popup):
    def __init__(self, stack_id, object_name="", chunk_key="", **kwargs):
        super().__init__(**kwargs)
        self.title = f"{object_name}  \u00b7  {chunk_key}"
        self.size_hint = (0.85, 0.75)
        self.auto_dismiss = True

        layout = BoxLayout(orientation='vertical', spacing=8, padding=8)
        self._img_widget = KivyImage(allow_stretch=True, keep_ratio=True)
        self._status = Label(text='Loading\u2026', size_hint_y=None, height=30,
                             font_size='13sp')
        layout.add_widget(self._status)
        layout.add_widget(self._img_widget)
        self.content = layout

        # Check cache first
        cached = AppState().thumbnail_cache.get(stack_id)
        if cached:
            self._show(cached)
        else:
            threading.Thread(
                target=self._fetch, args=(stack_id,), daemon=True).start()

    def _fetch(self, stack_id):
        from ..services.crowdsky_client import fetch_thumbnail
        try:
            data = fetch_thumbnail(stack_id)
            AppState().thumbnail_cache[stack_id] = data
            Clock.schedule_once(lambda dt: self._show(data))
        except Exception as e:
            msg = str(e)
            Clock.schedule_once(lambda dt: self._error(msg))

    def _show(self, data):
        img = CoreImage(BytesIO(data), ext='png')
        self._img_widget.texture = img.texture
        self._status.text = ''
        self._status.height = 0

    def _error(self, msg):
        self._status.text = f'Error: {msg}'
