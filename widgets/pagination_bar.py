"""PaginationBar: Page navigation widget for the gallery."""

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.metrics import dp, sp
from kivy.properties import NumericProperty


class PaginationBar(BoxLayout):
    """Numbered page buttons with previous/next navigation."""

    __events__ = ('on_page_changed',)

    current_page = NumericProperty(1)
    total_pages = NumericProperty(1)

    def update(self, current, total):
        """Rebuild page buttons for the given state."""
        self.current_page = current
        self.total_pages = total
        self.clear_widgets()

        if total <= 1:
            self.add_widget(Label(
                text='Page 1 / 1', font_size=sp(13),
                color=(0.55, 0.55, 0.60, 1),
            ))
            return

        # << button
        self._add_nav_btn('\u00ab', max(1, current - 5))
        # < button
        self._add_nav_btn('<', max(1, current - 1))

        # Determine which page numbers to show (up to 5 around current)
        pages = self._visible_pages(current, total)
        prev_p = 0
        for p in pages:
            if prev_p and p > prev_p + 1:
                self.add_widget(Label(
                    text='..', font_size=sp(12),
                    color=(0.55, 0.55, 0.60, 1),
                    size_hint_x=None, width=dp(24),
                ))
            self._add_page_btn(p, is_current=(p == current))
            prev_p = p

        # > button
        self._add_nav_btn('>', min(total, current + 1))
        # >> button
        self._add_nav_btn('\u00bb', min(total, current + 5))

    @staticmethod
    def _visible_pages(current, total):
        """Return list of page numbers to display."""
        pages = set()
        pages.add(1)
        pages.add(total)
        for offset in range(-2, 3):
            p = current + offset
            if 1 <= p <= total:
                pages.add(p)
        return sorted(pages)

    def _add_page_btn(self, page, is_current=False):
        btn = Button(
            text=str(page),
            font_size=sp(12),
            size_hint_x=None, width=dp(34),
            size_hint_y=None, height=dp(32),
            background_color=(0.20, 0.60, 1.0, 1) if is_current
                             else (0.22, 0.22, 0.30, 1),
            color=(1, 1, 1, 1),
            bold=is_current,
        )
        btn.bind(on_release=lambda b, p=page: self._go_page(p))
        self.add_widget(btn)

    def _add_nav_btn(self, text, target_page):
        btn = Button(
            text=text,
            font_size=sp(13),
            size_hint_x=None, width=dp(30),
            size_hint_y=None, height=dp(32),
            background_color=(0.18, 0.18, 0.24, 1),
            color=(0.7, 0.7, 0.75, 1),
        )
        btn.bind(on_release=lambda b, p=target_page: self._go_page(p))
        self.add_widget(btn)

    def _go_page(self, page):
        if page != self.current_page:
            self.dispatch('on_page_changed', page)

    def on_page_changed(self, page):
        """Default handler (required by Kivy event system)."""
        pass
