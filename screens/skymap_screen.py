"""SkyMapScreen: Interactive sky map and timeline with filters."""

from kivy.uix.screenmanager import Screen

from ..app_state import AppState
from ..widgets.thumbnail_popup import ThumbnailPopup


class SkyMapScreen(Screen):

    def on_enter(self):
        self.ids.filter_bar.build_from_state()
        self.ids.filter_bar.bind(on_filter_changed=self._on_filter_changed)
        self.ids.sky_map.bind(on_stack_tap=self._on_stack_tap)
        self.ids.timeline.bind(on_stack_tap=self._on_stack_tap)
        self._refresh_widgets()

    def on_leave(self):
        self.ids.filter_bar.unbind(on_filter_changed=self._on_filter_changed)
        self.ids.sky_map.unbind(on_stack_tap=self._on_stack_tap)
        self.ids.timeline.unbind(on_stack_tap=self._on_stack_tap)

    def _refresh_widgets(self):
        state = AppState()
        stacks = state.filtered_stacks or []
        self.ids.sky_map.set_stacks(stacks)
        self.ids.timeline.set_stacks(stacks)

    def _on_filter_changed(self, *args):
        self._refresh_widgets()

    def _on_stack_tap(self, widget, stack_id, chunk_key, object_name):
        ThumbnailPopup(
            stack_id=stack_id,
            object_name=object_name,
            chunk_key=chunk_key,
        ).open()

    def go_back(self):
        self.manager.current = "home"
