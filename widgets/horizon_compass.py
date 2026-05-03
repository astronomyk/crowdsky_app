"""8-point compass widget — set a minimum altitude per cardinal direction.

Produces a list of 8 floats in 0-90 deg, indexed N=0, NE=1, …, NW=7
(clockwise).  The compass is drawn as concentric arcs; tapping a slice
opens a small popup spinner so the user can set the altitude block for
that direction.
"""

from __future__ import annotations

import math

from kivy.clock import Clock
from kivy.uix.widget import Widget
from kivy.uix.popup import Popup
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.graphics import Color, Line, Ellipse
from kivy.core.text import Label as CoreLabel
from kivy.properties import ListProperty
from kivy.metrics import dp, sp

from ..services.plan_builder import COMPASS_DIRS


# Altitude levels offered in the popup picker (degrees above horizon).
LEVELS = [0, 15, 30, 45, 60, 75, 90]


class HorizonCompass(Widget):
    """Widget for editing 8 per-direction altitude blockers."""

    altitudes = ListProperty([0.0] * 8)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(size=self._redraw, pos=self._redraw,
                  altitudes=self._redraw)
        # Inside a ScrollView the parent layout sometimes finalises our
        # width across multiple frames, and not every intermediate value
        # fires the size bind reliably.  Retry the initial paint until
        # we see a credible widget width.
        self._initial_attempts = 0
        Clock.schedule_once(self._try_initial_paint, 0)

    def _try_initial_paint(self, _dt):
        self._initial_attempts += 1
        if self.width < dp(150) and self._initial_attempts < 30:
            Clock.schedule_once(self._try_initial_paint, 0)
            return
        self._redraw()

    def _redraw(self, *_):
        self.canvas.clear()
        if self.width <= 0 or self.height <= 0:
            return
        # Ensure Kivy actually flushes the new instructions in the next
        # draw cycle — without this, intermediate canvas state from
        # earlier (pre-layout) paints can stick around on screen.
        self.canvas.ask_update()

        cx = self.center_x
        cy = self.center_y
        r_outer = min(self.width, self.height) / 2.0 - dp(8)
        if r_outer <= 0:
            return

        with self.canvas:
            # Background rings (10° steps for context)
            Color(0.55, 0.55, 0.60, 0.25)
            for frac in (0.25, 0.5, 0.75):
                d = r_outer * 2 * frac
                Ellipse(pos=(cx - d / 2, cy - d / 2), size=(d, d), segments=72)

            # Outer ring (horizon)
            Color(0.55, 0.55, 0.60, 0.55)
            Line(circle=(cx, cy, r_outer), width=1.1)

            # 8-direction blocking polygon — vertex radius shrinks as
            # altitude increases.  Inset r_max slightly so an alt=0
            # vertex never sits exactly on the outer ring (where the
            # two lines overlap and visually cancel each other out).
            r_max = r_outer - dp(3)
            pts = []
            for i in range(8):
                az = math.radians(90 - i * 45)   # N at top
                alt = max(0.0, min(90.0, float(self.altitudes[i])))
                r = r_max * (1.0 - alt / 90.0)
                pts.extend([cx + r * math.cos(az), cy + r * math.sin(az)])
            Color(0.95, 0.30, 0.25, 0.85)
            Line(points=pts, width=1.6, close=True)

            # Direction tick marks at outer ring
            Color(0.85, 0.85, 0.90, 0.7)
            for i in range(8):
                az = math.radians(90 - i * 45)
                r0 = r_outer * 0.94
                r1 = r_outer
                Line(points=[cx + r0 * math.cos(az),
                             cy + r0 * math.sin(az),
                             cx + r1 * math.cos(az),
                             cy + r1 * math.sin(az)], width=1.0)

            # Direction labels just outside the ring
            for i, name in enumerate(COMPASS_DIRS):
                az = math.radians(90 - i * 45)
                r = r_outer + dp(10)
                lx = cx + r * math.cos(az)
                ly = cy + r * math.sin(az)
                lbl_text = f"{name}\n{int(self.altitudes[i])}°"
                core = CoreLabel(text=lbl_text, font_size=sp(10),
                                 halign="center", valign="middle")
                core.refresh()
                tex = core.texture
                Color(0.90, 0.90, 0.95, 1)
                from kivy.graphics import Rectangle
                Rectangle(texture=tex,
                          pos=(lx - tex.size[0] / 2,
                               ly - tex.size[1] / 2),
                          size=tex.size)

    # ------------------------------------------------------------------
    # Touch handling — tap opens the per-direction picker
    # ------------------------------------------------------------------

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False
        cx = self.center_x
        cy = self.center_y
        dx = touch.x - cx
        dy = touch.y - cy
        r = math.hypot(dx, dy)
        r_outer = min(self.width, self.height) / 2.0 - dp(8)
        if r_outer <= 0 or r > r_outer + dp(20) or r < dp(8):
            return False
        # azimuth where N is up, increasing clockwise
        ang = math.degrees(math.atan2(dx, dy)) % 360.0
        idx = int(round(ang / 45.0)) % 8
        self._open_picker(idx)
        return True

    def _open_picker(self, idx: int):
        title = f"Block at {COMPASS_DIRS[idx]} (deg above horizon)"
        layout = BoxLayout(orientation="vertical", spacing=dp(6),
                           padding=dp(8))
        grid = BoxLayout(orientation="horizontal", spacing=dp(4))
        popup_holder = {}

        def _set(val):
            new = list(self.altitudes)
            new[idx] = float(val)
            self.altitudes = new
            popup_holder["popup"].dismiss()

        for lvl in LEVELS:
            b = Button(text=f"{lvl}°", font_size=sp(13))
            b.bind(on_release=lambda _b, v=lvl: _set(v))
            grid.add_widget(b)
        layout.add_widget(Label(text=title, size_hint_y=None,
                                 height=dp(28)))
        layout.add_widget(grid)
        popup = Popup(title="", content=layout,
                      size_hint=(None, None), size=(dp(360), dp(140)),
                      separator_height=0,
                      background_color=(0.14, 0.14, 0.20, 1))
        popup_holder["popup"] = popup
        popup.open()
