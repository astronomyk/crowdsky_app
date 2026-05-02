"""Sky map showing the Hunt+24 shortlist + a planned subset.

Lightweight RA/Dec scatter — all candidate clusters drawn in dim grey,
the chosen targets drawn larger and in green with text labels.
"""

from __future__ import annotations

import math

from kivy.uix.widget import Widget
from kivy.graphics import Color, Ellipse, Line, Rectangle
from kivy.core.text import Label as CoreLabel
from kivy.properties import ListProperty
from kivy.metrics import dp, sp


class PlanSkyMap(Widget):
    """RA (0-24h) on x, Dec (-90..+90) on y, with two layers."""

    # List of dicts: {ra_deg, dec_deg, [name]} — drawn small/grey
    candidates = ListProperty([])
    # List of dicts: {ra_deg, dec_deg, name, [start_min]} — drawn highlighted
    selected = ListProperty([])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(size=self._redraw, pos=self._redraw,
                  candidates=self._redraw, selected=self._redraw)

    # ------------------------------------------------------------------
    # Coordinate transforms
    # ------------------------------------------------------------------

    def _xy(self, ra_deg: float, dec_deg: float) -> tuple[float, float]:
        # RA on x:   0..360 deg → left..right (origin at left)
        # Dec on y:  -90..+90  → bottom..top
        margin_l = dp(28)
        margin_r = dp(8)
        margin_b = dp(20)
        margin_t = dp(8)
        plot_w = max(1.0, self.width - margin_l - margin_r)
        plot_h = max(1.0, self.height - margin_b - margin_t)
        x = self.x + margin_l + (ra_deg / 360.0) * plot_w
        y = self.y + margin_b + ((dec_deg + 90.0) / 180.0) * plot_h
        return x, y

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _redraw(self, *_):
        self.canvas.clear()
        if self.width <= 0 or self.height <= 0:
            return

        with self.canvas:
            # Dark background
            Color(0.06, 0.06, 0.10, 1)
            Rectangle(pos=self.pos, size=self.size)

            # Frame
            Color(0.30, 0.32, 0.38, 1)
            x0, y0 = self._xy(0, -90)
            x1, y1 = self._xy(360, 90)
            Line(rectangle=(x0, y0, x1 - x0, y1 - y0), width=1.0)

            # Equator (Dec=0)
            Color(0.30, 0.32, 0.38, 0.6)
            ex0, ey0 = self._xy(0, 0)
            ex1, ey1 = self._xy(360, 0)
            Line(points=[ex0, ey0, ex1, ey1], width=0.8)

            # Hour grid lines every 4h
            for ra_h in (4, 8, 12, 16, 20):
                gx0, gy0 = self._xy(ra_h * 15, -90)
                gx1, gy1 = self._xy(ra_h * 15, 90)
                Color(0.30, 0.32, 0.38, 0.4)
                Line(points=[gx0, gy0, gx1, gy1], width=0.6)

            # Candidates (small grey dots)
            Color(0.5, 0.5, 0.6, 0.45)
            r = dp(2.0)
            for c in self.candidates:
                ra = c.get("ra_deg")
                dec = c.get("dec_deg")
                if ra is None or dec is None:
                    continue
                x, y = self._xy(float(ra), float(dec))
                Ellipse(pos=(x - r, y - r), size=(2 * r, 2 * r))

            # Selected targets (larger green dots + name labels)
            r2 = dp(5.0)
            for t in self.selected:
                ra = t.get("ra_deg")
                dec = t.get("dec_deg")
                if ra is None or dec is None:
                    continue
                x, y = self._xy(float(ra), float(dec))
                Color(0.20, 0.85, 0.30, 0.95)
                Ellipse(pos=(x - r2, y - r2), size=(2 * r2, 2 * r2))
                # Label
                name = str(t.get("name", ""))[:14]
                core = CoreLabel(text=name, font_size=sp(10))
                core.refresh()
                tex = core.texture
                Color(0.90, 0.95, 0.90, 1)
                Rectangle(texture=tex,
                          pos=(x + dp(6),
                               y - tex.size[1] / 2),
                          size=tex.size)

            # Axis tick labels
            Color(0.7, 0.7, 0.75, 1)
            for ra_h in (0, 6, 12, 18, 24):
                tx, _ = self._xy(min(ra_h * 15, 359.99), -90)
                lbl = CoreLabel(text=f"{ra_h}h", font_size=sp(9))
                lbl.refresh()
                Rectangle(texture=lbl.texture,
                          pos=(tx - lbl.texture.size[0] / 2,
                               self.y + dp(2)),
                          size=lbl.texture.size)
            for dec in (-60, -30, 0, 30, 60):
                _, ty = self._xy(0, dec)
                lbl = CoreLabel(text=f"{dec:+d}°", font_size=sp(9))
                lbl.refresh()
                Rectangle(texture=lbl.texture,
                          pos=(self.x + dp(4),
                               ty - lbl.texture.size[1] / 2),
                          size=lbl.texture.size)
