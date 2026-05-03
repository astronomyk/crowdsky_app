"""Build a tonight's-observation plan from prefs + constraints.

The output dict matches the format expected by
:func:`seestarpy.plan.set_view_plan`, plus a ``summary`` list for the
UI and bookkeeping fields (lat, lon, start time).

The selection step is intentionally simple — a random pick from
candidates that satisfy visibility, name class, and FOV constraints —
because the long-term plan is to swap in a CrowdSky-driven scheduler.
The :class:`TargetSource` indirection in ``target_source.py`` lets that
swap happen without touching this module.
"""

from __future__ import annotations

import math
import random
import warnings
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable

from .target_catalogue import Cluster, filter_by_name_class
from .target_source import TargetSource, get_default_source


# Compass labels used by HorizonCompass.  Index 0 = N, going clockwise.
COMPASS_DIRS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


# Seestar FOV per known model — (RA-direction, Dec-direction) in degrees.
# Convention matches seestarpy.plan: first dim = RA on sky (short pixel axis),
# second dim = Dec on sky (long pixel axis).
#
# Computed from sensor dimensions × pixel scale:
#   S50:     1920 × 1080 @ 2.4"/px  →  0.72° × 1.28° (rounded to seestarpy's
#                                       canonical 0.75 × 1.33)
#   S30 Pro: 2160 × 3840 @ 4.0"/px  →  2.40° × 4.27°
#   S30:     1024 × 1980 @ 4.0"/px  →  1.14° × 2.20°
#
# S30 Pro must come before S30 in iteration order so the substring match
# below picks the more specific model first.
SEESTAR_FOV = {
    "Seestar S50":     (0.75, 1.33),
    "Seestar S30 Pro": (2.40, 4.27),
    "Seestar S30":     (1.14, 2.20),
}
DEFAULT_FOV = (0.75, 1.33)


def fov_for_model(model: str) -> tuple[float, float]:
    if not model:
        return DEFAULT_FOV
    for key, fov in SEESTAR_FOV.items():
        if key.lower() in model.lower():
            return fov
    return DEFAULT_FOV


@dataclass
class HorizonMask:
    """Minimum altitude (deg) above the horizon for each of 8 azimuths.

    ``alts[i]`` corresponds to ``COMPASS_DIRS[i]`` (N=0, NE=1, ..., NW=7).
    Altitude limit at an arbitrary azimuth is found by linear interpolation
    between the two flanking compass points.
    """

    alts: list[float]

    @classmethod
    def clear(cls) -> "HorizonMask":
        return cls(alts=[0.0] * 8)

    def min_alt_at(self, az_deg: float) -> float:
        az = az_deg % 360.0
        idx = az / 45.0
        i0 = int(math.floor(idx)) % 8
        i1 = (i0 + 1) % 8
        frac = idx - math.floor(idx)
        return self.alts[i0] * (1 - frac) + self.alts[i1] * frac


@dataclass
class PlanPrefs:
    blocks_per_target: int = 4         # 1 block = 15 min
    allow_mosaic: bool = False
    name_class: str = "any"            # 'messier' | 'ngc' | 'any'
    radius_mode: str = "r50"           # 'core' | 'r50' | 'tidal'
    lp_filter: bool = False
    plan_name: str = "CrowdSky tonight"
    max_targets: int = 12
    min_altitude_deg: float = 30.0     # global altitude floor (deg above horizon)


# ---------------------------------------------------------------------------
# Visibility — Alt/Az computation via astropy
# ---------------------------------------------------------------------------

def _altaz_for(
    cluster: Cluster,
    when_utc: datetime,
    lat_deg: float,
    lon_deg: float,
) -> tuple[float, float]:
    """Compute (alt_deg, az_deg) for *cluster* at the given UTC time."""
    from astropy.coordinates import EarthLocation, SkyCoord, AltAz
    from astropy.time import Time
    import astropy.units as u

    loc = EarthLocation(lat=lat_deg * u.deg, lon=lon_deg * u.deg)
    obstime = Time(when_utc)
    target = SkyCoord(ra=cluster.ra_deg * u.deg, dec=cluster.dec_deg * u.deg)
    altaz = target.transform_to(AltAz(obstime=obstime, location=loc))
    return float(altaz.alt.deg), float(altaz.az.deg)


def _is_visible(
    cluster: Cluster,
    when_utc: datetime,
    lat_deg: float,
    lon_deg: float,
    mask: HorizonMask,
    min_alt_deg: float = 0.0,
) -> bool:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            alt, az = _altaz_for(cluster, when_utc, lat_deg, lon_deg)
    except Exception:
        return False
    if alt < min_alt_deg:
        return False
    return alt >= mask.min_alt_at(az)


# ---------------------------------------------------------------------------
# Plan assembly
# ---------------------------------------------------------------------------

def _minutes_since_local_midnight(dt_local: datetime, ref_midnight: datetime) -> int:
    delta = dt_local - ref_midnight
    return int(delta.total_seconds() // 60)


def _new_target_id(used: set[int]) -> int:
    while True:
        tid = random.randint(100_000_000, 999_999_999)
        if tid not in used:
            used.add(tid)
            return tid


def _mosaic_panels(
    cluster: Cluster,
    radius_deg: float,
    fov_w_deg: float,
    fov_h_deg: float,
    duration_min: int,
    start_min: int,
    used_ids: set[int],
    lp_filter: bool,
) -> list[dict]:
    """Build seestarpy-format target dicts for a mosaic over a cluster."""
    width = max(2 * radius_deg, fov_w_deg)
    height = max(2 * radius_deg, fov_h_deg)
    delta_ra = fov_w_deg * 0.85         # 15% overlap
    delta_dec = fov_h_deg * 0.85

    # Defer to seestarpy's mosaic planner so we share its boustrophedon
    # logic and cos(dec) correction.
    from seestarpy.plan import create_mosaic_plan
    sub = create_mosaic_plan(
        plan_name=cluster.name,
        center_ra=cluster.ra_hours,
        center_dec=cluster.dec_deg,
        width=width,
        height=height,
        delta_ra=delta_ra,
        delta_dec=delta_dec,
        t_total=duration_min,
        start_min=start_min,
        lp_filter=lp_filter,
        target_name_prefix=cluster.name.replace(" ", "_"),
    )
    panels = []
    for t in sub["list"]:
        # Replace the random ids from create_mosaic_plan with our own
        # bookkeeping to keep the global pool unique.
        t = dict(t)
        t["target_id"] = _new_target_id(used_ids)
        panels.append(t)
    return panels


def build_plan(
    *,
    lat_deg: float,
    lon_deg: float,
    start_local: datetime,
    prefs: PlanPrefs,
    mask: HorizonMask,
    fov_deg: tuple[float, float] = DEFAULT_FOV,
    source: TargetSource | None = None,
    rng: random.Random | None = None,
) -> dict:
    """Compose a plan dict + summary.

    The schedule starts at *start_local* (rounded up to the next 15-min
    boundary) and continues until either ``prefs.max_targets`` are
    scheduled or 6 hours of clock time have been booked.  Targets are
    drawn at random from candidates that pass visibility + name-class
    filters at the midpoint of their slot.
    """
    src = source or get_default_source()
    rng = rng or random.Random()
    fov_w, fov_h = fov_deg
    fov_min_dim = min(fov_w, fov_h)

    # Round start up to next 15-min boundary so durations align with chunk grid.
    minute_block = (start_local.minute // 15 + 1) * 15
    if minute_block >= 60:
        anchor = start_local.replace(
            minute=0, second=0, microsecond=0) + timedelta(hours=1)
    else:
        anchor = start_local.replace(
            minute=minute_block, second=0, microsecond=0)

    midnight = anchor.replace(hour=0, minute=0, second=0, microsecond=0)

    candidates = list(filter_by_name_class(src.candidates(), prefs.name_class))
    rng.shuffle(candidates)

    duration_min = prefs.blocks_per_target * 15
    used_ids: set[int] = set()
    summary: list[dict] = []
    seestar_list: list[dict] = []

    cursor = anchor
    horizon_end = anchor + timedelta(hours=6)
    chosen_names: set[str] = set()

    while (
        len(summary) < prefs.max_targets
        and cursor < horizon_end
        and candidates
    ):
        slot_mid_local = cursor + timedelta(minutes=duration_min // 2)
        slot_mid_utc = datetime.utcfromtimestamp(slot_mid_local.timestamp())

        pick: Cluster | None = None
        for c in candidates:
            if c.name in chosen_names:
                continue
            if not _is_visible(c, slot_mid_utc, lat_deg, lon_deg, mask,
                                min_alt_deg=prefs.min_altitude_deg):
                continue
            radius = c.radius_deg(prefs.radius_mode)
            too_big = radius > (fov_min_dim / 2.0)
            if too_big and not prefs.allow_mosaic:
                continue
            pick = c
            break

        if pick is None:
            break

        chosen_names.add(pick.name)
        radius = pick.radius_deg(prefs.radius_mode)
        too_big = radius > (fov_min_dim / 2.0)

        start_min = _minutes_since_local_midnight(cursor, midnight)

        display = pick.display_name()
        if too_big and prefs.allow_mosaic:
            panels = _mosaic_panels(
                cluster=pick,
                radius_deg=radius,
                fov_w_deg=fov_w,
                fov_h_deg=fov_h,
                duration_min=duration_min,
                start_min=start_min,
                used_ids=used_ids,
                lp_filter=prefs.lp_filter,
            )
            seestar_list.extend(panels)
            n_panels = len(panels)
        else:
            tid = _new_target_id(used_ids)
            seestar_list.append({
                "target_id": tid,
                "target_name": display,
                "alias_name": pick.name if display != pick.name else "",
                "target_ra_dec": [pick.ra_hours, pick.dec_deg],
                "lp_filter": prefs.lp_filter,
                "start_min": start_min,
                "duration_min": duration_min,
            })
            n_panels = 1

        summary.append({
            "name": display,
            "catalogue_name": pick.name,
            "ra_deg": pick.ra_deg,
            "dec_deg": pick.dec_deg,
            "blocks": prefs.blocks_per_target,
            "duration_min": duration_min,
            "start_min": start_min,
            "panels": n_panels,
            "mosaic": n_panels > 1,
            "radius_deg": radius,
            "dist_pc": pick.dist_pc,
            "n_stars": pick.n_stars,
        })
        cursor += timedelta(minutes=duration_min)

    return {
        "plan_name": prefs.plan_name,
        "update_time_seestar": start_local.strftime("%Y.%m.%d"),
        "list": seestar_list,
        "summary": summary,
        "lat": lat_deg,
        "lon": lon_deg,
        "start_local": anchor.isoformat(),
        "fov_deg": list(fov_deg),
        "source": src.name,
    }


def to_seestar_payload(plan: dict) -> dict:
    """Strip the local-only fields before pushing to the device."""
    return {
        "plan_name": plan["plan_name"],
        "update_time_seestar": plan["update_time_seestar"],
        "list": plan["list"],
    }
