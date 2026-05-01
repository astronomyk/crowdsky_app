"""Native Kivy Canvas timeline — date jitter plot with pinch zoom, pan, tap.

Enhanced from v2: filter-based dot coloring, tap shows ThumbnailPopup.
"""

import math
import hashlib
from datetime import datetime

from kivy.uix.widget import Widget
from kivy.properties import ListProperty
from kivy.graphics import Color, Ellipse, Line, Rectangle
from kivy.core.text import Label as CoreLabel
from kivy.metrics import dp, sp


FILTER_COLORS = {
    "IRCUT": (0.97, 0.32, 0.29, 0.8),
    "LP":    (0.35, 0.65, 1.0, 0.8),
}
DEFAULT_DOT_COLOR = (0.20, 0.60, 1.0, 0.7)


class TimelineWidget(Widget):
    __events__ = ('on_stack_tap',)

    stacks_data = ListProperty([])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._parsed = []     # [(timestamp_float, jitter_y_frac, stack_dict)]
        self._t_range = [0, 1]
        self._dot_positions = []   # [(cx, cy, stack_dict)]
        self._touches = []
        self._touch_start_x = None
        self._start_t_range = None
        self._pinch_start_dist = 0
        self._pinch_start_t_range = None
        self._pinch_center_x = 0
        self.bind(stacks_data=self._on_data_change)
        self.bind(size=self._redraw, pos=self._redraw)

    def set_stacks(self, stacks):
        self.stacks_data = stacks

    def _on_data_change(self, *_):
        self._parse_dates()
        self._redraw()

    def _parse_dates(self):
        self._parsed = []
        for s in self.stacks_data:
            dos = s.get("date_obs_start", "")
            if not dos:
                continue
            try:
                dt = datetime.strptime(dos[:19], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                try:
                    dt = datetime.strptime(dos[:19], "%Y-%m-%dT%H:%M:%S")
                except ValueError:
                    continue
            ts = dt.timestamp()
            key = str(s.get("id", s.get("chunk_key", dos)))
            h = int(hashlib.md5(key.encode()).hexdigest()[:8], 16)
            jitter = (h % 1000) / 1000.0
            self._parsed.append((ts, jitter, s))

        if self._parsed:
            ts_values = [p[0] for p in self._parsed]
            t_min, t_max = min(ts_values), max(ts_values)
            if t_min == t_max:
                t_min -= 86400
                t_max += 86400
            margin = (t_max - t_min) * 0.05
            self._t_range = [t_min - margin, t_max + margin]

    def _ts_to_x(self, ts):
        t0, t1 = self._t_range
        span = t1 - t0
        if span == 0:
            return self.x + self.width / 2
        ml = dp(10)
        mr = dp(10)
        inner_w = self.width - ml - mr
        frac = (ts - t0) / span
        return self.x + ml + frac * inner_w

    def _zoom(self, factor, px):
        ml = dp(10)
        inner_w = self.width - ml - dp(10)
        t0, t1 = self._t_range
        frac = (px - self.x - ml) / max(inner_w, 1)
        t_at = t0 + frac * (t1 - t0)
        self._t_range = [t_at - (t_at - t0) * factor,
                         t_at + (t1 - t_at) * factor]
        self._redraw()

    def _redraw(self, *_):
        self.canvas.clear()
        if self.width < dp(50) or self.height < dp(30):
            return

        ml = dp(10)
        mr = dp(10)
        mb = dp(18)
        mt = dp(6)
        inner_x = self.x + ml
        inner_y = self.y + mb
        inner_w = self.width - ml - mr
        inner_h = self.height - mb - mt

        with self.canvas:
            Color(0.10, 0.10, 0.15, 1)
            Rectangle(pos=self.pos, size=self.size)

            Color(0.08, 0.08, 0.12, 1)
            Rectangle(pos=(inner_x, inner_y), size=(inner_w, inner_h))

            Color(0.20, 0.20, 0.26, 1)
            Line(points=[inner_x, inner_y, inner_x + inner_w, inner_y],
                 width=1)

        if not self._parsed:
            self._draw_label("No data", self.center_x, self.center_y,
                             font_size=sp(11), color=(0.55, 0.55, 0.60, 1))
            return

        # Date tick labels
        t0, t1 = self._t_range
        span = t1 - t0
        n_ticks = max(3, min(6, int(inner_w / dp(70))))
        for i in range(n_ticks + 1):
            frac = i / n_ticks
            ts = t0 + frac * span
            x = self._ts_to_x(ts)
            try:
                dt = datetime.fromtimestamp(ts)
                label = dt.strftime("%b %d")
            except (OSError, ValueError):
                label = ""
            self._draw_label(label, x, self.y + dp(2),
                             anchor_x="center", anchor_y="bottom",
                             font_size=sp(8), color=(0.45, 0.45, 0.50, 1))
            with self.canvas:
                Color(0.20, 0.20, 0.26, 0.5)
                Line(points=[x, inner_y, x, inner_y + inner_h], width=1)

        # Dots
        self._dot_positions = []
        with self.canvas:
            for ts, jitter, s in self._parsed:
                x = self._ts_to_x(ts)
                y = inner_y + dp(3) + jitter * (inner_h - dp(6))
                if not (inner_x <= x <= inner_x + inner_w):
                    continue
                fname = s.get("filter_name", "")
                color = FILTER_COLORS.get(fname, DEFAULT_DOT_COLOR)
                Color(*color)
                r = dp(3)
                Ellipse(pos=(x - r, y - r), size=(r * 2, r * 2))
                self._dot_positions.append((x, y, s))

    def _draw_label(self, text, x, y, anchor_x="center", anchor_y="center",
                    font_size=None, color=None):
        if font_size is None:
            font_size = sp(10)
        if color is None:
            color = (0.55, 0.55, 0.60, 1)
        label = CoreLabel(text=text, font_size=font_size)
        label.refresh()
        tex = label.texture
        tw, th = tex.size
        if anchor_x == "center":
            dx = x - tw / 2
        elif anchor_x == "right":
            dx = x - tw
        else:
            dx = x
        if anchor_y == "center":
            dy = y - th / 2
        elif anchor_y == "top":
            dy = y - th
        else:
            dy = y
        with self.canvas:
            Color(*color)
            Rectangle(texture=tex, pos=(dx, dy), size=tex.size)

    # --- Touch handling ---

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False

        if hasattr(touch, 'button') and touch.button in (
                'scrolldown', 'scrollup'):
            factor = 1.2 if touch.button == 'scrolldown' else 1 / 1.2
            self._zoom(factor, touch.x)
            return True

        if touch.is_double_tap:
            self._parse_dates()
            self._redraw()
            return True

        touch.grab(self)
        self._touches.append(touch)
        if len(self._touches) == 1:
            self._touch_start_x = touch.x
            self._start_t_range = list(self._t_range)
        elif len(self._touches) == 2:
            t1, t2 = self._touches
            self._pinch_start_dist = abs(t2.x - t1.x)
            self._pinch_start_t_range = list(self._t_range)
            self._pinch_center_x = (t1.x + t2.x) / 2
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is not self:
            return False

        if len(self._touches) == 2:
            t1, t2 = self._touches
            dist = abs(t2.x - t1.x)
            if self._pinch_start_dist > 0:
                factor = self._pinch_start_dist / max(dist, 1)
                self._t_range = list(self._pinch_start_t_range)
                self._zoom(factor, self._pinch_center_x)
            return True

        if self._touch_start_x is None or self._start_t_range is None:
            return True
        dx = touch.x - self._touch_start_x
        ml = dp(10)
        inner_w = self.width - ml - dp(10)
        t_span = self._start_t_range[1] - self._start_t_range[0]
        t_shift = -dx / max(inner_w, 1) * t_span
        self._t_range = [self._start_t_range[0] + t_shift,
                         self._start_t_range[1] + t_shift]
        self._redraw()
        return True

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            if touch in self._touches:
                self._touches.remove(touch)
            touch.ungrab(self)
            if len(self._touches) == 0 and self._touch_start_x is not None:
                dx = touch.x - self._touch_start_x
                if abs(dx) < dp(12):
                    self._handle_tap(touch.x, touch.y)
            return True
        return False

    def _handle_tap(self, tx, ty):
        best, best_dist = None, dp(25)
        for (cx, cy, s) in self._dot_positions:
            d = math.hypot(cx - tx, cy - ty)
            if d < best_dist:
                best_dist = d
                best = s
        if best and best.get('id') is not None:
            self.dispatch('on_stack_tap',
                          best['id'],
                          best.get('chunk_key', ''),
                          best.get('object_name', 'Unknown'))

    def on_stack_tap(self, stack_id, chunk_key, object_name):
        pass
