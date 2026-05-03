"""PlanResultScreen: review the built plan + push it to the Seestar."""

from __future__ import annotations

import threading

from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.metrics import dp, sp
from kivy.properties import (StringProperty, BooleanProperty,
                             ListProperty)

from ..app_state import AppState
from ..services.target_catalogue import load_shortlist
from ..services.plan_executor import push_plan


def _fmt_time(start_min: int) -> str:
    """Minutes-since-local-midnight → HH:MM (wrapping past 24h)."""
    h = (start_min // 60) % 24
    m = start_min % 60
    return f"{h:02d}:{m:02d}"


def _fmt_ra(ra_deg: float) -> str:
    h = (ra_deg / 15.0) % 24
    hh = int(h)
    mm = int(round((h - hh) * 60))
    if mm == 60:
        hh = (hh + 1) % 24
        mm = 0
    return f"{hh:02d}h{mm:02d}m"


def _fmt_dec(dec_deg: float) -> str:
    sign = "+" if dec_deg >= 0 else "-"
    a = abs(dec_deg)
    d = int(a)
    m = int(round((a - d) * 60))
    if m == 60:
        d += 1
        m = 0
    return f"{sign}{d:02d}°{m:02d}'"


class PlanResultScreen(Screen):
    is_busy = BooleanProperty(False)
    status = StringProperty("")
    headline = StringProperty("")
    plan_summary = ListProperty([])

    def on_pre_enter(self):
        state = AppState()
        plan = state.pending_plan
        if not plan:
            self.headline = "No plan available"
            self.plan_summary = []
            self._fill_summary([])
            self.ids.skymap.selected = []
            return

        summary = list(plan.get("summary", []))
        self.plan_summary = summary

        # Headline
        n_targets = len(summary)
        n_panels = sum(s["panels"] for s in summary)
        n_mos = sum(1 for s in summary if s["mosaic"])
        if n_targets == 0:
            self.headline = "No targets fit the constraints — adjust prefs"
        else:
            self.headline = (f"{n_targets} target(s), {n_panels} panel(s), "
                              f"{n_mos} mosaic(s) — source: "
                              f"{plan.get('source', 'Hunt+24 shortlist')}")

        # Sky map: faint candidate dots + highlighted selections
        try:
            clusters = load_shortlist()
            self.ids.skymap.candidates = [
                {"ra_deg": c.ra_deg, "dec_deg": c.dec_deg, "name": c.name}
                for c in clusters
            ]
        except Exception:
            self.ids.skymap.candidates = []
        self.ids.skymap.selected = [
            {"name": s["name"], "ra_deg": s["ra_deg"], "dec_deg": s["dec_deg"]}
            for s in summary
        ]

        # Summary card rows
        self._fill_summary(summary)
        self.status = ""

    def _fill_summary(self, summary):
        container = self.ids.summary_list
        container.clear_widgets()
        if not summary:
            container.add_widget(Label(
                text="(no targets)", font_size=sp(12),
                color=(0.55, 0.55, 0.60, 1),
                size_hint_y=None, height=dp(28)))
            return
        for s in summary:
            row = BoxLayout(orientation="vertical", size_hint_y=None,
                            height=dp(54), padding=[dp(8), dp(4)],
                            spacing=dp(2))
            top = BoxLayout(orientation="horizontal", size_hint_y=None,
                            height=dp(20))
            name_lbl = Label(text=s["name"], font_size=sp(13),
                              bold=True, color=(0.95, 0.95, 1, 1),
                              halign="left", valign="middle")
            name_lbl.bind(size=name_lbl.setter("text_size"))
            top.add_widget(name_lbl)
            extra = ""
            if s.get("mosaic"):
                extra = f"  · mosaic ×{s['panels']}"
            time_lbl = Label(
                text=f"{_fmt_time(s['start_min'])} → "
                     f"{_fmt_time(s['start_min'] + s['duration_min'])}{extra}",
                font_size=sp(12), color=(0.20, 0.85, 0.30, 1),
                halign="right", valign="middle",
                size_hint_x=None, width=dp(170))
            time_lbl.bind(size=time_lbl.setter("text_size"))
            top.add_widget(time_lbl)

            coord_lbl = Label(
                text=f"RA {_fmt_ra(s['ra_deg'])}    "
                     f"Dec {_fmt_dec(s['dec_deg'])}    "
                     f"({s['blocks']} block(s))",
                font_size=sp(11), color=(0.70, 0.72, 0.78, 1),
                halign="left", valign="middle", size_hint_y=None,
                height=dp(18))
            coord_lbl.bind(size=coord_lbl.setter("text_size"))

            row.add_widget(top)
            row.add_widget(coord_lbl)
            container.add_widget(row)

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def do_execute(self):
        state = AppState()
        if not state.pending_plan or not state.plan_seestar_ip:
            self.status = "No plan or no Seestar selected"
            return
        self.is_busy = True
        self.status = "Pushing plan to Seestar..."
        threading.Thread(target=self._execute_thread, daemon=True).start()

    def _execute_thread(self):
        state = AppState()
        try:
            resp = push_plan(state.plan_seestar_ip, state.pending_plan)
            Clock.schedule_once(lambda dt: self._on_executed(resp))
        except Exception as exc:
            msg = str(exc)
            Clock.schedule_once(lambda dt: self._on_execute_error(msg))

    def _on_executed(self, resp):
        self.is_busy = False
        code = resp.get("code") if isinstance(resp, dict) else None
        if code == 0:
            self.status = "Plan accepted by Seestar"
        else:
            self.status = f"Seestar response: {resp}"

    def _on_execute_error(self, msg):
        self.is_busy = False
        self.status = f"Push error: {msg}"

    def go_back(self):
        self.manager.current = "plan"
