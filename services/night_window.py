"""Compute tonight's night window: sunset/midnight/sunrise + visible sky.

Used by PlanResultScreen to overlay the part of the sky that's actually
observable on the planning night.  All times returned are naive
``datetime`` in *local* time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class NightWindow:
    sunset_local: datetime
    midnight_local: datetime
    sunrise_local: datetime
    lst_sunset_deg: float
    lst_midnight_deg: float
    lst_sunrise_deg: float
    # Cells covering the part of the sky visible (max alt > min_alt) at
    # any sample point during the night.  Each entry is
    # (ra_deg, dec_deg, ra_w_deg, dec_h_deg) — the lower-left corner
    # plus extent of a tile on the RA/Dec grid.
    visible_cells: list[tuple[float, float, float, float]] = field(
        default_factory=list)


def _to_utc_naive(dt_local: datetime) -> datetime:
    """Naive local datetime → naive UTC datetime via system tz."""
    return datetime.utcfromtimestamp(dt_local.timestamp())


def compute_horizons(
    lat_deg: float,
    lon_deg: float,
    ref_local: datetime,
) -> tuple[datetime, datetime, datetime] | None:
    """Find the next sunset → sunrise pair for the given location.

    Scans noon → noon+24 h in 5-minute steps and returns
    ``(sunset_local, midnight_local, sunrise_local)`` as naive local
    datetimes.  Returns ``None`` if the sun never crosses the horizon
    in that window (polar day / night) or if astropy is unavailable.
    """
    try:
        from astropy.coordinates import EarthLocation, AltAz, get_sun
        from astropy.time import Time
        import astropy.units as u
    except ImportError:
        return None

    loc = EarthLocation(lat=lat_deg * u.deg, lon=lon_deg * u.deg)
    start_local = ref_local.replace(hour=12, minute=0, second=0,
                                    microsecond=0)
    n = 24 * 12
    sample_locals = [start_local + timedelta(minutes=5 * i)
                     for i in range(n)]
    sample_utcs = [_to_utc_naive(t) for t in sample_locals]
    times = Time(sample_utcs)
    sun_alts = get_sun(times).transform_to(
        AltAz(obstime=times, location=loc)).alt.deg

    sunset_idx = None
    sunrise_idx = None
    for i in range(1, n):
        a0, a1 = sun_alts[i - 1], sun_alts[i]
        if sunset_idx is None and a0 >= 0 and a1 < 0:
            sunset_idx = i
        elif sunset_idx is not None and a0 < 0 and a1 >= 0:
            sunrise_idx = i
            break
    if sunset_idx is None or sunrise_idx is None:
        return None

    sunset_local = sample_locals[sunset_idx]
    sunrise_local = sample_locals[sunrise_idx]
    midnight_local = sunset_local + (sunrise_local - sunset_local) / 2
    return sunset_local, midnight_local, sunrise_local


def compute_night_window(
    lat_deg: float,
    lon_deg: float,
    ref_local: datetime,
    *,
    min_alt_deg: float = 30.0,
    grid_step_deg: int = 10,
) -> NightWindow | None:
    """Find sunset/midnight/sunrise + the visible-tonight grid.

    Parameters
    ----------
    lat_deg, lon_deg : float
        Observer location in decimal degrees (E and N positive).
    ref_local : datetime
        A naive local datetime that picks the night.  We start the
        search at noon on the same calendar day and look 24 h forward.
    min_alt_deg : float
        Altitude threshold for "visible".
    grid_step_deg : int
        RA/Dec grid resolution for the visible-region map.

    Returns
    -------
    NightWindow or None
        ``None`` if the sun never crosses the horizon during the
        24 h window (polar day / night).
    """
    try:
        import numpy as np
        from astropy.coordinates import (
            EarthLocation, SkyCoord, AltAz, get_sun)
        from astropy.time import Time
        import astropy.units as u
    except ImportError:
        return None

    loc = EarthLocation(lat=lat_deg * u.deg, lon=lon_deg * u.deg)

    # Sample noon → noon+24h in 5-minute steps to find sun horizon crossings.
    start_local = ref_local.replace(hour=12, minute=0, second=0,
                                    microsecond=0)
    n = 24 * 12  # 5-minute steps for 24h
    sample_locals = [start_local + timedelta(minutes=5 * i)
                     for i in range(n)]
    sample_utcs = [_to_utc_naive(t) for t in sample_locals]
    times = Time(sample_utcs)
    altazframe = AltAz(obstime=times, location=loc)
    sun_alts = get_sun(times).transform_to(altazframe).alt.deg

    sunset_idx = None
    sunrise_idx = None
    for i in range(1, n):
        a0, a1 = sun_alts[i - 1], sun_alts[i]
        if sunset_idx is None and a0 >= 0 and a1 < 0:
            sunset_idx = i
        elif sunset_idx is not None and a0 < 0 and a1 >= 0:
            sunrise_idx = i
            break
    if sunset_idx is None or sunrise_idx is None:
        return None

    sunset_local = sample_locals[sunset_idx]
    sunrise_local = sample_locals[sunrise_idx]
    midnight_local = sunset_local + (sunrise_local - sunset_local) / 2

    sunset_utc = _to_utc_naive(sunset_local)
    midnight_utc = _to_utc_naive(midnight_local)
    sunrise_utc = _to_utc_naive(sunrise_local)

    def _lst_deg(dt_utc):
        return float(Time(dt_utc).sidereal_time(
            "apparent", longitude=lon_deg * u.deg).deg)

    lst_sunset = _lst_deg(sunset_utc)
    lst_midnight = _lst_deg(midnight_utc)
    lst_sunrise = _lst_deg(sunrise_utc)

    # Visible-region grid: for each cell, take the max altitude over
    # five sample times across the night.
    step = grid_step_deg
    ra_centers = np.arange(0.0, 360.0, step) + step / 2.0
    dec_centers = np.arange(-90.0 + step / 2.0, 90.0, step)
    RA, DEC = np.meshgrid(ra_centers, dec_centers)
    sky = SkyCoord(ra=RA * u.deg, dec=DEC * u.deg)

    night_secs = (sunrise_local - sunset_local).total_seconds()
    sample_times_utc = [
        sunset_utc + timedelta(seconds=night_secs * f)
        for f in (0.0, 0.25, 0.5, 0.75, 1.0)
    ]
    max_alt = np.full(RA.shape, -90.0)
    for t_utc in sample_times_utc:
        altaz = sky.transform_to(AltAz(obstime=Time(t_utc), location=loc))
        max_alt = np.maximum(max_alt, altaz.alt.deg)

    visible_cells: list[tuple[float, float, float, float]] = []
    mask = max_alt >= min_alt_deg
    rows, cols = np.where(mask)
    for r, c in zip(rows.tolist(), cols.tolist()):
        ra = float(RA[r, c]) - step / 2.0
        dec = float(DEC[r, c]) - step / 2.0
        visible_cells.append((ra, dec, float(step), float(step)))

    return NightWindow(
        sunset_local=sunset_local,
        midnight_local=midnight_local,
        sunrise_local=sunrise_local,
        lst_sunset_deg=lst_sunset,
        lst_midnight_deg=lst_midnight,
        lst_sunrise_deg=lst_sunrise,
        visible_cells=visible_cells,
    )
