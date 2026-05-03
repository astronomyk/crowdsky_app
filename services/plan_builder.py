"""Build a tonight's-observation plan from prefs + constraints.

Algorithm (v2 — meridian-priority):

1. The night runs from anchor (now, rounded up to the next 15-min mark)
   to sunrise, computed via :func:`night_window.compute_horizons`.
2. The night is divided into fixed-length slots of
   ``prefs.blocks_per_target × 15`` minutes — that's how many targets
   we'll schedule.
3. For each slot:
     a. Compute LST at the slot's mid-time.
     b. Compute alt + |HA| for every candidate (closed-form, vectorised).
     c. Keep candidates that pass visibility (min_altitude_deg + the
        8-direction horizon mask) and that haven't been scheduled yet.
     d. Sort the survivors by |HA| ascending — i.e. closest to the
        meridian at slot-midtime first.
     e. Random-pick from the top 10.
4. If a slot has no visible survivors, leave it empty and move on.

The output matches :func:`seestarpy.plan.set_view_plan`, plus a
``summary`` list for the UI.  Mosaic packing has been removed for now
(targets larger than the FOV are scheduled as a single centre pointing).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np

from .target_catalogue import Cluster, filter_by_name_class
from .target_source import TargetSource, get_default_source
from .night_window import compute_horizons


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

    def min_alt_array(self, az_deg_array: np.ndarray) -> np.ndarray:
        """Vectorised :meth:`min_alt_at` for a 1-D array of azimuths."""
        az = np.mod(az_deg_array, 360.0)
        idx = az / 45.0
        i0 = np.floor(idx).astype(int) % 8
        i1 = (i0 + 1) % 8
        frac = idx - np.floor(idx)
        alts = np.asarray(self.alts, dtype=float)
        return alts[i0] * (1.0 - frac) + alts[i1] * frac


@dataclass
class PlanPrefs:
    blocks_per_target: int = 4         # 1 block = 15 min
    name_class: str = "any"            # 'messier' | 'ngc' | 'any'
    radius_mode: str = "r50"           # 'core' | 'r50' | 'tidal' (display only)
    lp_filter: bool = False
    plan_name: str = "CrowdSky tonight"
    min_altitude_deg: float = 30.0     # global altitude floor (deg above horizon)
    top_k_pool: int = 10               # how many meridian-closest to pick from


# ---------------------------------------------------------------------------
# Vectorised alt/az from spherical trig — much faster than astropy for our
# use case and accurate to << 0.1° (refraction etc. don't matter for a
# "is this above 30°?" check).
# ---------------------------------------------------------------------------

def _altaz_arrays(
    ra_deg: np.ndarray,
    dec_deg: np.ndarray,
    lat_deg: float,
    lst_deg: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return ``(alt_deg, az_deg, ha_deg)`` for arrays of RA/Dec.

    ``ha_deg`` is wrapped to ``[-180, +180]`` so that ``|ha|`` measures
    distance to the meridian directly.
    """
    ha_deg = (lst_deg - ra_deg + 180.0) % 360.0 - 180.0
    sin_lat = math.sin(math.radians(lat_deg))
    cos_lat = math.cos(math.radians(lat_deg))
    dec_rad = np.radians(dec_deg)
    ha_rad = np.radians(ha_deg)
    sin_dec = np.sin(dec_rad)
    cos_dec = np.cos(dec_rad)
    sin_alt = sin_lat * sin_dec + cos_lat * cos_dec * np.cos(ha_rad)
    sin_alt = np.clip(sin_alt, -1.0, 1.0)
    alt_deg = np.degrees(np.arcsin(sin_alt))
    cos_alt = np.cos(np.radians(alt_deg))
    safe_cos_alt = np.where(np.abs(cos_alt) < 1e-9, 1e-9, cos_alt)
    sin_az = -cos_dec * np.sin(ha_rad) / safe_cos_alt
    cos_az = ((sin_dec - sin_lat * sin_alt)
              / (cos_lat * safe_cos_alt))
    az_deg = np.degrees(np.arctan2(sin_az, cos_az)) % 360.0
    return alt_deg, az_deg, ha_deg


def _lst_deg(when_utc: datetime, lon_deg: float) -> float:
    """Apparent local sidereal time in degrees, via astropy."""
    from astropy.time import Time
    import astropy.units as u
    return float(Time(when_utc).sidereal_time(
        "apparent", longitude=lon_deg * u.deg).deg)


# ---------------------------------------------------------------------------
# Plan assembly
# ---------------------------------------------------------------------------

def _minutes_since_local_midnight(dt_local: datetime,
                                  ref_midnight: datetime) -> int:
    delta = dt_local - ref_midnight
    return int(delta.total_seconds() // 60)


def _new_target_id(used: set[int]) -> int:
    while True:
        tid = random.randint(100_000_000, 999_999_999)
        if tid not in used:
            used.add(tid)
            return tid


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

    See module docstring for the algorithm.  Returns a plan dict (which
    may have an empty ``list`` if no candidates were visible at any
    slot during the night).
    """
    src = source or get_default_source()
    rng = rng or random.Random()

    # 1. Anchor on the next 15-min boundary.
    minute_block = (start_local.minute // 15 + 1) * 15
    if minute_block >= 60:
        anchor = start_local.replace(
            minute=0, second=0, microsecond=0) + timedelta(hours=1)
    else:
        anchor = start_local.replace(
            minute=minute_block, second=0, microsecond=0)
    midnight = anchor.replace(hour=0, minute=0, second=0, microsecond=0)

    # 2. Find sunrise — the night ends there.  Fall back to anchor + 8h
    # if astropy is unavailable or we're at a polar latitude.
    horizons = compute_horizons(lat_deg, lon_deg, anchor)
    night_end = (horizons[2] if horizons is not None
                 else anchor + timedelta(hours=8))
    if night_end <= anchor:
        night_end = anchor + timedelta(hours=8)

    # 3. Slot count.
    duration_min = max(15, int(prefs.blocks_per_target) * 15)
    night_min = (night_end - anchor).total_seconds() / 60.0
    n_slots = int(night_min // duration_min)

    # 4. Candidate pool.
    candidates = list(filter_by_name_class(src.candidates(),
                                           prefs.name_class))

    plan: dict = {
        "plan_name": prefs.plan_name,
        "update_time_seestar": anchor.strftime("%Y.%m.%d"),
        "list": [],
        "summary": [],
        "lat": lat_deg,
        "lon": lon_deg,
        "start_local": anchor.isoformat(),
        "fov_deg": list(fov_deg),
        "source": src.name,
    }

    if not candidates or n_slots <= 0:
        return plan

    ras = np.array([c.ra_deg for c in candidates])
    decs = np.array([c.dec_deg for c in candidates])

    used_ids: set[int] = set()
    chosen_names: set[str] = set()

    for slot_idx in range(n_slots):
        slot_start = anchor + timedelta(minutes=slot_idx * duration_min)
        slot_mid = slot_start + timedelta(minutes=duration_min / 2)
        slot_mid_utc = datetime.utcfromtimestamp(slot_mid.timestamp())

        try:
            lst_deg = _lst_deg(slot_mid_utc, lon_deg)
        except Exception:
            continue

        alt_deg, az_deg, ha_deg = _altaz_arrays(
            ras, decs, lat_deg, lst_deg)
        mask_floor = mask.min_alt_array(az_deg)
        floor = np.maximum(mask_floor, prefs.min_altitude_deg)
        visible = alt_deg >= floor
        # Exclude already-chosen
        chosen_arr = np.array([c.name in chosen_names for c in candidates])
        ok = visible & ~chosen_arr

        if not np.any(ok):
            continue

        idx_visible = np.where(ok)[0]
        # Sort visible candidates by |HA| ascending — meridian first.
        order = idx_visible[np.argsort(np.abs(ha_deg[idx_visible]))]
        top = order[: max(1, prefs.top_k_pool)]
        chosen_idx = int(rng.choice(top))
        pick = candidates[chosen_idx]
        chosen_names.add(pick.name)

        start_min = _minutes_since_local_midnight(slot_start, midnight)
        display = pick.display_name()
        plan["list"].append({
            "target_id": _new_target_id(used_ids),
            "target_name": display,
            "alias_name": pick.name if display != pick.name else "",
            "target_ra_dec": [pick.ra_hours, pick.dec_deg],
            "lp_filter": prefs.lp_filter,
            "start_min": start_min,
            "duration_min": duration_min,
        })
        plan["summary"].append({
            "name": display,
            "catalogue_name": pick.name,
            "ra_deg": pick.ra_deg,
            "dec_deg": pick.dec_deg,
            "blocks": prefs.blocks_per_target,
            "duration_min": duration_min,
            "start_min": start_min,
            "panels": 1,
            "mosaic": False,
            "alt_deg": float(alt_deg[chosen_idx]),
            "ha_deg": float(ha_deg[chosen_idx]),
            "radius_deg": pick.radius_deg(prefs.radius_mode),
            "dist_pc": pick.dist_pc,
            "n_stars": pick.n_stars,
        })

    return plan


def to_seestar_payload(plan: dict) -> dict:
    """Strip the local-only fields before pushing to the device."""
    return {
        "plan_name": plan["plan_name"],
        "update_time_seestar": plan["update_time_seestar"],
        "list": plan["list"],
    }
