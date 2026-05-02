"""PlanScreen: build a 'tonight' observing plan and push it to a Seestar."""

from __future__ import annotations

import threading
from datetime import datetime

from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.checkbox import CheckBox
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.metrics import dp, sp
from kivy.properties import (StringProperty, BooleanProperty,
                             NumericProperty, ListProperty)

from ..app_state import AppState
from ..services.seestar_service import find_seestars
from ..services.target_scanner import get_device_info
from ..services.target_catalogue import load_shortlist
from ..services.target_source import get_default_source
from ..services.plan_builder import (
    HorizonMask, PlanPrefs, build_plan, fov_for_model,
)
from ..services.plan_executor import push_plan, get_seestar_location


RADIUS_MODES = ["core", "r50", "tidal"]
NAME_CLASSES = ["messier", "ngc", "any"]


class PlanScreen(Screen):
    is_busy = BooleanProperty(False)
    status = StringProperty("")
    selected_seestar_ip = StringProperty("")

    blocks_per_target = NumericProperty(4)
    allow_mosaic = BooleanProperty(False)
    name_class_idx = NumericProperty(2)        # 0=messier 1=ngc 2=any
    radius_mode_idx = NumericProperty(1)       # 0=core 1=r50 2=tidal
    lp_filter = BooleanProperty(False)

    plan_summary = ListProperty([])
    has_plan = BooleanProperty(False)

    location_text = StringProperty("Location: —")
    fov_text = StringProperty("FOV: —")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._device_info = {}    # {ip: (serial, model)}
        self._location = None     # (lat, lon)
        self._fov = None          # (w, h)
        self._plan = None         # last build_plan() output

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_enter(self):
        # Pre-populate candidate skymap
        try:
            clusters = load_shortlist()
            self.ids.skymap.candidates = [
                {"ra_deg": c.ra_deg, "dec_deg": c.dec_deg, "name": c.name}
                for c in clusters
            ]
        except Exception as exc:
            self.status = f"Catalogue error: {exc}"
        # Show known seestars if any have been discovered already
        if AppState().available_seestars:
            self._build_seestar_radio_list()

    # ------------------------------------------------------------------
    # Seestar discovery (mirrors DonateSeestarScreen)
    # ------------------------------------------------------------------

    def do_scan_network(self):
        n = int(self.ids.seestar_count.text)
        self.is_busy = True
        self.status = "Scanning for Seestars..."
        threading.Thread(target=self._scan_thread, args=(n,),
                         daemon=True).start()

    def _scan_thread(self, n):
        try:
            seestars = find_seestars(n)
            info = {}
            for hostname, ip in seestars.items():
                if ip in info:
                    continue
                info[ip] = get_device_info(ip)
            Clock.schedule_once(
                lambda dt: self._on_scan_done(seestars, info))
        except Exception as exc:
            msg = str(exc)
            Clock.schedule_once(lambda dt: self._on_scan_error(msg))

    def _on_scan_done(self, seestars, info):
        AppState().available_seestars.update(seestars)
        self._device_info.update(info)
        self.is_busy = False
        n = len(AppState().available_seestars)
        self.status = f"Found {n} Seestar(s)"
        self._build_seestar_radio_list()

    def _on_scan_error(self, msg):
        self.is_busy = False
        self.status = f"Scan error: {msg}"

    def _build_seestar_radio_list(self):
        container = self.ids.seestar_list
        container.clear_widgets()
        seen = set()
        for hostname, ip in AppState().available_seestars.items():
            if ip in seen:
                continue
            seen.add(ip)
            serial, model = self._device_info.get(ip, ("", ""))

            row = BoxLayout(orientation="horizontal", size_hint_y=None,
                            height=dp(40), spacing=dp(8),
                            padding=[dp(8), 0])
            cb = CheckBox(group="plan_seestar", size_hint_x=None,
                          width=dp(32),
                          active=(self.selected_seestar_ip == ip))
            _ip = ip
            cb.bind(active=lambda inst, val, sip=_ip:
                    self._on_seestar_selected(sip, val))
            row.add_widget(cb)
            txt = serial or ip
            if model:
                txt += f"  ({model})"
            txt += f"  [{ip}]"
            lbl = Label(text=txt, font_size=sp(13),
                         color=(0.9, 0.9, 0.95, 1),
                         halign="left", valign="middle")
            lbl.bind(size=lbl.setter("text_size"))
            row.add_widget(lbl)
            container.add_widget(row)

    def _on_seestar_selected(self, ip, active):
        if not active:
            return
        self.selected_seestar_ip = ip
        _, model = self._device_info.get(ip, ("", ""))
        self._fov = fov_for_model(model)
        self.fov_text = f"FOV: {self._fov[0]:.2f}° × {self._fov[1]:.2f}°"
        self.is_busy = True
        self.status = f"Reading location from {ip}..."
        threading.Thread(target=self._fetch_location_thread,
                         args=(ip,), daemon=True).start()

    def _fetch_location_thread(self, ip):
        loc = get_seestar_location(ip)
        Clock.schedule_once(lambda dt: self._on_location(loc))

    def _on_location(self, loc):
        self.is_busy = False
        if loc is None:
            self._location = None
            self.location_text = "Location: unavailable (using PC tz only)"
            self.status = "Could not read location from Seestar"
            return
        lat, lon = loc
        self._location = (lat, lon)
        self.location_text = f"Location: {lat:+.3f}°, {lon:+.3f}°"
        self.status = "Ready to plan"

    # ------------------------------------------------------------------
    # Build plan
    # ------------------------------------------------------------------

    def do_build_plan(self):
        if not self.selected_seestar_ip:
            self.status = "Select a Seestar first"
            return
        if self._location is None:
            self.status = "Location not available — re-select a Seestar"
            return
        self.is_busy = True
        self.status = "Building plan..."
        threading.Thread(target=self._build_thread, daemon=True).start()

    def _build_thread(self):
        try:
            mask = HorizonMask(alts=list(self.ids.horizon.altitudes))
            prefs = PlanPrefs(
                blocks_per_target=int(self.blocks_per_target),
                allow_mosaic=bool(self.allow_mosaic),
                name_class=NAME_CLASSES[int(self.name_class_idx)],
                radius_mode=RADIUS_MODES[int(self.radius_mode_idx)],
                lp_filter=bool(self.lp_filter),
            )
            lat, lon = self._location
            plan = build_plan(
                lat_deg=lat,
                lon_deg=lon,
                start_local=datetime.now(),
                prefs=prefs,
                mask=mask,
                fov_deg=self._fov or fov_for_model(""),
                source=get_default_source(),
            )
            Clock.schedule_once(lambda dt: self._on_plan_built(plan))
        except Exception as exc:
            msg = str(exc)
            Clock.schedule_once(lambda dt: self._on_plan_error(msg))

    def _on_plan_built(self, plan):
        self.is_busy = False
        self._plan = plan
        self.plan_summary = list(plan["summary"])
        self.has_plan = bool(self.plan_summary)
        self.ids.skymap.selected = [
            {"name": s["name"],
             "ra_deg": s["ra_deg"], "dec_deg": s["dec_deg"]}
            for s in self.plan_summary
        ]
        n_panels = sum(s["panels"] for s in self.plan_summary)
        n_mos = sum(1 for s in self.plan_summary if s["mosaic"])
        if not self.plan_summary:
            self.status = "No targets fit the constraints"
        else:
            self.status = (f"{len(self.plan_summary)} target(s), "
                            f"{n_panels} panel(s), {n_mos} mosaic(s)")

    def _on_plan_error(self, msg):
        self.is_busy = False
        self.status = f"Plan error: {msg}"

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def do_execute_plan(self):
        if not self._plan or not self.selected_seestar_ip:
            return
        self.is_busy = True
        self.status = "Pushing plan to Seestar..."
        threading.Thread(target=self._execute_thread, daemon=True).start()

    def _execute_thread(self):
        try:
            resp = push_plan(self.selected_seestar_ip, self._plan)
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
        self.manager.current = "home"
