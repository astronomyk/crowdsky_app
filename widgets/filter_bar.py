"""FilterBar: Shared filter controls for Sky Map and Gallery screens."""

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.checkbox import CheckBox
from kivy.uix.label import Label
from kivy.metrics import dp, sp
from kivy.properties import StringProperty

from ..app_state import AppState


class FilterBar(BoxLayout):
    """Horizontal bar with filter-name, object, and telescope filters.

    Dispatches ``on_filter_changed`` when any filter is modified.
    """

    __events__ = ('on_filter_changed',)

    filter_label = StringProperty("Filters: All")

    def build_from_state(self):
        """Rebuild filter controls from AppState filter options."""
        self.clear_widgets()
        state = AppState()

        # --- Filter-name toggle buttons: All / IRCUT / LP ---
        filter_group = BoxLayout(
            orientation='horizontal', spacing=dp(2), size_hint_x=0.45)

        btn_all = ToggleButton(
            text='All', group='filter_name', state='down',
            font_size=sp(11), size_hint_y=None, height=dp(32),
            background_color=(0.25, 0.25, 0.32, 1),
        )
        btn_all.bind(on_release=lambda b: self._set_filter_name(None))
        filter_group.add_widget(btn_all)

        for fname, color in [('IRCUT', (0.6, 0.2, 0.2, 1)),
                              ('LP', (0.2, 0.3, 0.6, 1))]:
            if fname in state.available_filter_names:
                btn = ToggleButton(
                    text=fname, group='filter_name',
                    font_size=sp(11), size_hint_y=None, height=dp(32),
                    background_color=color,
                )
                btn.bind(
                    on_release=lambda b, fn=fname: self._set_filter_name(fn))
                filter_group.add_widget(btn)

        # Restore current toggle state
        if state.filter_name_filter:
            for child in filter_group.children:
                if (isinstance(child, ToggleButton)
                        and child.text == state.filter_name_filter):
                    child.state = 'down'
                    btn_all.state = 'normal'

        self.add_widget(filter_group)

        # --- Object dropdown button ---
        obj_label = self._obj_label_text(state)
        obj_btn = Button(
            text=obj_label, font_size=sp(11),
            size_hint_x=0.3, size_hint_y=None, height=dp(32),
            background_color=(0.22, 0.22, 0.30, 1),
        )
        obj_btn.bind(on_release=lambda b: self._open_multi_select(
            'Object', state.available_objects, state.object_filters,
            self._set_object_filters))
        self.add_widget(obj_btn)
        self._obj_btn = obj_btn

        # --- Telescope dropdown button ---
        tel_label = self._tel_label_text(state)
        tel_btn = Button(
            text=tel_label, font_size=sp(11),
            size_hint_x=0.25, size_hint_y=None, height=dp(32),
            background_color=(0.22, 0.22, 0.30, 1),
        )
        tel_btn.bind(on_release=lambda b: self._open_multi_select(
            'Telescope', state.available_telescopes, state.telescope_filters,
            self._set_telescope_filters))
        self.add_widget(tel_btn)
        self._tel_btn = tel_btn

    @staticmethod
    def _obj_label_text(state):
        if not state.object_filters:
            return 'Obj: All'
        if len(state.object_filters) == 1:
            name = state.object_filters[0]
            return name if len(name) <= 10 else name[:8] + '..'
        return f'Obj: {len(state.object_filters)}'

    @staticmethod
    def _tel_label_text(state):
        if not state.telescope_filters:
            return 'Tel: All'
        if len(state.telescope_filters) == 1:
            return state.telescope_filters[0][:10]
        return f'Tel: {len(state.telescope_filters)}'

    def _set_filter_name(self, filter_name):
        state = AppState()
        state.filter_name_filter = filter_name
        state.apply_filters()
        self.dispatch('on_filter_changed')

    def _set_object_filters(self, selected):
        state = AppState()
        state.object_filters = selected
        state.apply_filters()
        self._obj_btn.text = self._obj_label_text(state)
        self.dispatch('on_filter_changed')

    def _set_telescope_filters(self, selected):
        state = AppState()
        state.telescope_filters = selected
        state.apply_filters()
        self._tel_btn.text = self._tel_label_text(state)
        self.dispatch('on_filter_changed')

    def _open_multi_select(self, title, options, current_selection, callback):
        """Open a popup with checkboxes for multi-select filtering."""
        popup_content = BoxLayout(orientation='vertical', spacing=dp(8),
                                  padding=dp(8))

        scroll = ScrollView(size_hint_y=1)
        checklist = BoxLayout(orientation='vertical', size_hint_y=None,
                              spacing=dp(4))
        checklist.bind(minimum_height=checklist.setter('height'))

        checkboxes = {}
        for option in options:
            row = BoxLayout(orientation='horizontal', size_hint_y=None,
                            height=dp(36), spacing=dp(8))
            cb = CheckBox(
                size_hint_x=None, width=dp(32),
                active=(option in current_selection),
            )
            lbl = Label(
                text=option, font_size=sp(13),
                color=(0.9, 0.9, 0.95, 1),
                halign='left', valign='middle',
            )
            lbl.bind(size=lbl.setter('text_size'))
            row.add_widget(cb)
            row.add_widget(lbl)
            checklist.add_widget(row)
            checkboxes[option] = cb

        scroll.add_widget(checklist)
        popup_content.add_widget(scroll)

        # Buttons row
        btn_row = BoxLayout(
            orientation='horizontal', size_hint_y=None, height=dp(40),
            spacing=dp(8))

        popup = Popup(
            title=f'Filter by {title}', content=popup_content,
            size_hint=(0.85, 0.7), auto_dismiss=True,
        )

        def apply(_):
            selected = [opt for opt, cb in checkboxes.items() if cb.active]
            callback(selected)
            popup.dismiss()

        def clear(_):
            callback([])
            popup.dismiss()

        apply_btn = Button(
            text='Apply', font_size=sp(14),
            background_color=(0.20, 0.60, 1.0, 1),
            color=(1, 1, 1, 1),
        )
        apply_btn.bind(on_release=apply)

        clear_btn = Button(
            text='Clear', font_size=sp(14),
            background_color=(0.3, 0.3, 0.35, 1),
            color=(1, 1, 1, 1),
        )
        clear_btn.bind(on_release=clear)

        btn_row.add_widget(clear_btn)
        btn_row.add_widget(apply_btn)
        popup_content.add_widget(btn_row)

        popup.open()

    def on_filter_changed(self, *args):
        """Default handler (required by Kivy event system)."""
        pass
