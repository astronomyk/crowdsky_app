"""Native Kivy Canvas sky map — RA/Dec scatter plot with pinch zoom and pan.

Enhanced from v2: filter-based dot coloring, default zoom to fit Dec axis,
Milky Way outline from d3-celestial GeoJSON data.
"""

import json
import math
import threading
from collections import Counter
from pathlib import Path

from kivy.uix.widget import Widget
from kivy.properties import ListProperty
from kivy.graphics import (Color, Ellipse, Line, Rectangle,
                           StencilPush, StencilUse, StencilUnUse, StencilPop)
from kivy.core.text import Label as CoreLabel
from kivy.clock import Clock
from kivy.metrics import dp, sp


FILTER_COLORS = {
    "IRCUT": (0.97, 0.32, 0.29, 0.8),   # #f85149
    "LP":    (0.35, 0.65, 1.0, 0.8),     # #58a6ff
}
DEFAULT_DOT_COLOR = (0.20, 0.60, 1.0, 0.7)

# Module-level MW outline cache: list of features or None (not yet loaded)
_mw_features = None
_mw_loading = False

_MW_CACHE_FILE = Path.home() / ".crowdsky" / "mw_outline.json"
_MW_CDN_URL = (
    "https://cdn.jsdelivr.net/gh/ofrohn/d3-celestial@master/data/mw.json"
)


def _load_mw_data(callback):
    """Load MW outline GeoJSON, from local cache or CDN.

    Parsing and ring extraction happen in the background thread.
    Calls callback(rings) on the main thread with a list of [(ra, dec), ...] rings.
    """
    global _mw_features, _mw_loading
    if _mw_features is not None or _mw_loading:
        return
    _mw_loading = True

    def _worker():
        global _mw_features, _mw_loading
        features = []
        # Try local cache first
        try:
            if _MW_CACHE_FILE.exists():
                data = json.loads(_MW_CACHE_FILE.read_text())
                features = data.get("features", [])
        except Exception:
            pass

        # Fetch from CDN if no cache
        if not features:
            try:
                import urllib.request
                raw = urllib.request.urlopen(_MW_CDN_URL, timeout=10).read()
                data = json.loads(raw)
                features = data.get("features", [])
                # Save to cache
                try:
                    _MW_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
                    _MW_CACHE_FILE.write_text(
                        json.dumps(data, separators=(",", ":")))
                except Exception:
                    pass
            except Exception:
                pass

        _mw_features = features
        _mw_loading = False

        # Extract rings in background thread (can be heavy)
        rings = _extract_mw_rings(features)
        Clock.schedule_once(lambda dt: callback(rings))

    threading.Thread(target=_worker, daemon=True).start()


def _extract_mw_rings(features):
    """Extract all polygon rings from MW features as lists of (ra_deg, dec_deg).

    The d3-celestial data uses [lon, lat] in degrees where lon is in [-180, 180].
    We convert to RA [0, 360] and split rings that cross the RA 0/360 boundary
    (same approach as the web UI in stacks.php).
    """
    if not features:
        return []
    rings = []
    for feat in features:
        for poly in feat["geometry"]["coordinates"]:
            for ring in poly:
                if len(ring) < 4:
                    continue
                # Convert to RA, skip duplicate closing vertex
                pts = [(p[0] % 360, p[1]) for p in ring[:-1]]
                n = len(pts)

                # Check for any RA 0/360 crossings (jumps > 180°)
                has_crossing = any(
                    abs(pts[(i + 1) % n][0] - pts[i][0]) > 180
                    for i in range(n)
                )

                if not has_crossing:
                    rings.append(pts)
                    continue

                # Split at RA 0/360 crossings
                segments = [[]]
                for i in range(n):
                    segments[-1].append(pts[i])
                    j = (i + 1) % n
                    d_ra = pts[j][0] - pts[i][0]
                    if abs(d_ra) > 180:
                        # Interpolate Dec at the boundary
                        end_b = 0 if d_ra > 0 else 360
                        start_b = 360 - end_b
                        frac = (end_b - pts[i][0]) / (
                            d_ra - 360 if d_ra > 0 else d_ra + 360)
                        mid_dec = pts[i][1] + frac * (pts[j][1] - pts[i][1])
                        segments[-1].append((end_b, mid_dec))
                        segments.append([(start_b, mid_dec)])

                # Merge first and last segments (ring is closed)
                if len(segments) > 1:
                    first = segments.pop(0)
                    segments[-1].extend(first)

                for seg in segments:
                    if len(seg) >= 3:
                        rings.append(seg)
    return rings


class SkyMapWidget(Widget):
    __events__ = ('on_stack_tap',)

    stacks_data = ListProperty([])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Default: show full Dec range, RA [90, 270]
        self.ra_range = [90, 270]
        self.dec_range = [-90, 90]
        self._point_groups = []
        self._dot_positions = []   # [(cx, cy, group_dict), ...]
        self._touches = []
        self._touch_start = None
        self._start_ra = None
        self._start_dec = None
        self._pinch_start_dist = 0
        self._pinch_start_ra = None
        self._pinch_start_dec = None
        self._pinch_center = (0, 0)
        self._mw_rings = []   # cached converted rings for drawing
        self.bind(stacks_data=self._on_data_change)
        self.bind(size=self._redraw, pos=self._redraw)
        # Start loading MW outline data in background
        _load_mw_data(self._on_mw_loaded)

    def _on_mw_loaded(self, rings):
        """Called on main thread when MW GeoJSON is ready."""
        self._mw_rings = rings
        self._redraw()

    def set_stacks(self, stacks):
        self.stacks_data = stacks

    def _on_data_change(self, *_):
        self._group_points()
        self._fit_default_zoom()
        self._redraw()

    def _group_points(self):
        """Group stacks by rounded (RA, Dec) at 0.1 degree resolution."""
        groups = {}
        for s in self.stacks_data:
            ra = s.get("ra_deg")
            dec = s.get("dec_deg")
            if ra is None or dec is None:
                continue
            try:
                ra = float(ra)
                dec = float(dec)
            except (ValueError, TypeError):
                continue
            key = (round(ra, 1), round(dec, 1))
            if key not in groups:
                groups[key] = {
                    "ra": key[0], "dec": key[1],
                    "count": 0,
                    "name": s.get("object_name", "Unknown"),
                    "representative_id": None,
                    "representative_chunk_key": None,
                    "filters": [],
                }
            groups[key]["count"] += 1
            groups[key]["filters"].append(s.get("filter_name", ""))
            groups[key]["representative_id"] = s.get("id")
            groups[key]["representative_chunk_key"] = s.get("chunk_key", "")

        # Compute dominant filter per group
        for g in groups.values():
            counts = Counter(f for f in g["filters"] if f)
            g["filter_name"] = counts.most_common(1)[0][0] if counts else ""
            del g["filters"]

        self._point_groups = list(groups.values())

    def _fit_default_zoom(self):
        """Default zoom: full Dec range (-90, +90), RA [90, 270]."""
        self.dec_range = [-90, 90]
        self.ra_range = [90, 270]

    def _ra_to_x(self, ra):
        r0, r1 = self.ra_range
        span = r1 - r0
        if span == 0:
            return self.x + self.width * 0.5
        margin = dp(40)
        inner_w = self.width - margin - dp(10)
        frac = (ra - r0) / span
        return self.x + margin + frac * inner_w

    def _dec_to_y(self, dec):
        d0, d1 = self.dec_range
        span = d1 - d0
        if span == 0:
            return self.y + self.height * 0.5
        margin_bottom = dp(26)
        margin_top = dp(10)
        inner_h = self.height - margin_bottom - margin_top
        frac = (dec - d0) / span
        return self.y + margin_bottom + frac * inner_h

    def _redraw(self, *_):
        self.canvas.clear()
        if self.width < dp(50) or self.height < dp(50):
            return

        margin_left = dp(40)
        margin_right = dp(10)
        margin_bottom = dp(26)
        margin_top = dp(10)
        inner_x = self.x + margin_left
        inner_y = self.y + margin_bottom
        inner_w = self.width - margin_left - margin_right
        inner_h = self.height - margin_bottom - margin_top

        with self.canvas:
            # Background
            Color(0.10, 0.10, 0.15, 1)
            Rectangle(pos=self.pos, size=self.size)

            # Plot area
            Color(0.08, 0.08, 0.12, 1)
            Rectangle(pos=(inner_x, inner_y), size=(inner_w, inner_h))

            # Grid lines
            Color(0.20, 0.20, 0.26, 1)
            ra_step = self._nice_step(self.ra_range[1] - self.ra_range[0], 6)
            dec_step = self._nice_step(self.dec_range[1] - self.dec_range[0], 6)

            ra = math.ceil(self.ra_range[0] / ra_step) * ra_step
            while ra <= self.ra_range[1]:
                x = self._ra_to_x(ra)
                if inner_x <= x <= inner_x + inner_w:
                    Line(points=[x, inner_y, x, inner_y + inner_h], width=1)
                ra += ra_step

            dec = math.ceil(self.dec_range[0] / dec_step) * dec_step
            while dec <= self.dec_range[1]:
                y = self._dec_to_y(dec)
                if inner_y <= y <= inner_y + inner_h:
                    Line(points=[inner_x, y, inner_x + inner_w, y], width=1)
                dec += dec_step

        # Milky Way band
        self._draw_milky_way(inner_x, inner_y, inner_w, inner_h)

        # Axis tick labels
        ra = math.ceil(self.ra_range[0] / ra_step) * ra_step
        while ra <= self.ra_range[1]:
            x = self._ra_to_x(ra)
            if inner_x <= x <= inner_x + inner_w:
                self._draw_label(f"{int(ra)}\u00b0", x, inner_y - dp(3),
                                 anchor_x="center", anchor_y="top",
                                 font_size=sp(9))
            ra += ra_step

        dec = math.ceil(self.dec_range[0] / dec_step) * dec_step
        while dec <= self.dec_range[1]:
            y = self._dec_to_y(dec)
            if inner_y <= y <= inner_y + inner_h:
                prefix = "+" if dec > 0 else ""
                self._draw_label(f"{prefix}{int(dec)}\u00b0",
                                 inner_x - dp(3), y,
                                 anchor_x="right", anchor_y="center",
                                 font_size=sp(9))
            dec += dec_step

        # Axis labels
        self._draw_label("RA", inner_x + inner_w / 2, self.y + dp(2),
                         anchor_x="center", anchor_y="bottom",
                         font_size=sp(10), color=(0.45, 0.45, 0.50, 1))
        self._draw_label("Dec", self.x + dp(2), inner_y + inner_h / 2,
                         anchor_x="left", anchor_y="center",
                         font_size=sp(10), color=(0.45, 0.45, 0.50, 1))

        # Dots
        self._dot_positions = []
        if not self._point_groups:
            self._draw_label("No data", self.center_x, self.center_y,
                             anchor_x="center", anchor_y="center",
                             font_size=sp(14), color=(0.55, 0.55, 0.60, 1))
            return

        max_count = max(p["count"] for p in self._point_groups)
        with self.canvas:
            for p in self._point_groups:
                x = self._ra_to_x(p["ra"])
                y = self._dec_to_y(p["dec"])
                if not (inner_x <= x <= inner_x + inner_w
                        and inner_y <= y <= inner_y + inner_h):
                    continue
                # Sqrt scale: radius 4dp to 14dp
                r = dp(4) + dp(10) * math.sqrt(
                    p["count"] / max(max_count, 1))
                color = FILTER_COLORS.get(
                    p.get("filter_name", ""), DEFAULT_DOT_COLOR)
                Color(*color)
                Ellipse(pos=(x - r, y - r), size=(r * 2, r * 2))
                self._dot_positions.append((x, y, p))

    def _draw_milky_way(self, inner_x, inner_y, inner_w, inner_h):
        """Draw the Milky Way outline from d3-celestial GeoJSON data.

        Uses batched Mesh and Line calls to minimise canvas instruction count.
        """
        if not self._mw_rings:
            # Data not loaded yet (or fetch failed) — try reloading
            if _mw_features is None and not _mw_loading:
                _load_mw_data(self._on_mw_loaded)
            return

        # Rings are already split at RA 0/360 crossings by _extract_mw_rings.
        # However some rings span the full sky without any single >180° jump,
        # so we also break outline segments at large pixel gaps.
        pixel_gap_threshold = inner_w * 0.3

        outline_segments = []

        for ring in self._mw_rings:
            # Convert ring to pixel coordinates
            current_line = []
            prev_x = None
            for ra_deg, dec_deg in ring:
                x = self._ra_to_x(ra_deg)
                y = self._dec_to_y(dec_deg)
                if prev_x is not None and abs(x - prev_x) > pixel_gap_threshold:
                    # Large jump — break the polyline
                    if len(current_line) >= 4:
                        outline_segments.append(current_line)
                    current_line = [x, y]
                else:
                    current_line.extend([x, y])
                prev_x = x
            if len(current_line) >= 4:
                outline_segments.append(current_line)

        # Draw outlines clipped to the plot area
        with self.canvas:
            StencilPush()
            Rectangle(pos=(inner_x, inner_y), size=(inner_w, inner_h))
            StencilUse()

            if outline_segments:
                Color(0.45, 0.50, 0.70, 0.25)
                for pts in outline_segments:
                    Line(points=pts, width=1.1)

            StencilUnUse()
            Rectangle(pos=(inner_x, inner_y), size=(inner_w, inner_h))
            StencilPop()

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

    def _nice_step(self, span, target_ticks):
        if span <= 0:
            return 1
        raw = span / max(target_ticks, 1)
        mag = 10 ** math.floor(math.log10(raw))
        normalized = raw / mag
        if normalized < 1.5:
            return mag
        elif normalized < 3.5:
            return 2 * mag
        elif normalized < 7.5:
            return 5 * mag
        else:
            return 10 * mag

    # --- Touch handling: pinch zoom, pan, tap ---

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False

        # Scroll wheel (desktop)
        if hasattr(touch, 'button') and touch.button in (
                'scrolldown', 'scrollup'):
            factor = 1.2 if touch.button == 'scrolldown' else 1 / 1.2
            self._zoom(factor, touch.x, touch.y)
            return True

        # Double-tap reset
        if touch.is_double_tap:
            self._fit_default_zoom()
            self._redraw()
            return True

        touch.grab(self)
        self._touches.append(touch)
        if len(self._touches) == 1:
            self._touch_start = (touch.x, touch.y)
            self._start_ra = list(self.ra_range)
            self._start_dec = list(self.dec_range)
        elif len(self._touches) == 2:
            t1, t2 = self._touches
            self._pinch_start_dist = math.hypot(t2.x - t1.x, t2.y - t1.y)
            self._pinch_start_ra = list(self.ra_range)
            self._pinch_start_dec = list(self.dec_range)
            self._pinch_center = ((t1.x + t2.x) / 2, (t1.y + t2.y) / 2)
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is not self:
            return False

        if len(self._touches) == 2:
            t1, t2 = self._touches
            dist = math.hypot(t2.x - t1.x, t2.y - t1.y)
            if self._pinch_start_dist > 0:
                factor = self._pinch_start_dist / max(dist, 1)
                cx, cy = self._pinch_center
                self.ra_range = list(self._pinch_start_ra)
                self.dec_range = list(self._pinch_start_dec)
                self._zoom(factor, cx, cy)
            return True

        # Single-touch pan
        if self._touch_start is None or self._start_ra is None:
            return True
        dx = touch.x - self._touch_start[0]
        dy = touch.y - self._touch_start[1]

        margin_left = dp(40)
        margin_right = dp(10)
        margin_bottom = dp(26)
        margin_top = dp(10)
        inner_w = self.width - margin_left - margin_right
        inner_h = self.height - margin_bottom - margin_top

        ra_span = self._start_ra[1] - self._start_ra[0]
        dec_span = self._start_dec[1] - self._start_dec[0]
        ra_shift = -dx / max(inner_w, 1) * ra_span
        dec_shift = -dy / max(inner_h, 1) * dec_span

        self.ra_range = [self._start_ra[0] + ra_shift,
                         self._start_ra[1] + ra_shift]
        self.dec_range = [self._start_dec[0] + dec_shift,
                          self._start_dec[1] + dec_shift]
        self._redraw()
        return True

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            if touch in self._touches:
                self._touches.remove(touch)
            touch.ungrab(self)
            if len(self._touches) == 0 and self._touch_start is not None:
                dx = touch.x - self._touch_start[0]
                dy = touch.y - self._touch_start[1]
                if math.hypot(dx, dy) < dp(12):
                    self._handle_tap(touch.x, touch.y)
            return True
        return False

    def _zoom(self, factor, px, py):
        margin_left = dp(40)
        margin_right = dp(10)
        margin_bottom = dp(26)
        margin_top = dp(10)
        inner_w = self.width - margin_left - margin_right
        inner_h = self.height - margin_bottom - margin_top
        inner_x = self.x + margin_left
        inner_y = self.y + margin_bottom

        ra_frac = (px - inner_x) / max(inner_w, 1)
        dec_frac = (py - inner_y) / max(inner_h, 1)
        ra_at = self.ra_range[0] + ra_frac * (
            self.ra_range[1] - self.ra_range[0])
        dec_at = self.dec_range[0] + dec_frac * (
            self.dec_range[1] - self.dec_range[0])

        ra_min, ra_max = self.ra_range
        dec_min, dec_max = self.dec_range
        self.ra_range = [ra_at - (ra_at - ra_min) * factor,
                         ra_at + (ra_max - ra_at) * factor]
        self.dec_range = [dec_at - (dec_at - dec_min) * factor,
                          dec_at + (dec_max - dec_at) * factor]
        self._redraw()

    def _handle_tap(self, tx, ty):
        best, best_dist = None, dp(40)
        for (cx, cy, group) in self._dot_positions:
            d = math.hypot(cx - tx, cy - ty)
            if d < best_dist:
                best_dist = d
                best = group
        if best and best.get('representative_id') is not None:
            self.dispatch('on_stack_tap',
                          best['representative_id'],
                          best['representative_chunk_key'],
                          best['name'])

    def on_stack_tap(self, stack_id, chunk_key, object_name):
        pass
