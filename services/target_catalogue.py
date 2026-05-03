"""Hunt+24 open-cluster shortlist loader.

Reads ``hunt24_shortlist.csv`` (sibling to ``main.py``) and exposes
:class:`Cluster` records along with simple classification helpers.

The shortlist is curated for Seestar S30/S50: 0.5 < area < 30 sq.deg,
distance < 2 kpc, N_stars > 100.  See ``Hunt+24_ReadMe.txt`` for full
column definitions of the parent catalogue.
"""

from __future__ import annotations

import csv
import math
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SHORTLIST_FILENAME = "hunt24_shortlist.csv"

# Match Messier / NGC / IC anywhere in a comma-separated name list.
_MESSIER_RE = re.compile(r"(?:^|,\s*)M(?:essier)?[\s_]*\d+\b", re.IGNORECASE)
_NGC_RE = re.compile(r"(?:^|,\s*)(?:NGC|IC)[\s_]*\d+\b", re.IGNORECASE)


@dataclass(frozen=True)
class Cluster:
    """One row of the Hunt+24 shortlist (post-enrichment)."""
    rank: int
    name: str
    ra_deg: float
    dec_deg: float
    glon_deg: float
    glat_deg: float
    dist_pc: float
    n_stars: int
    r50_pc: float
    r50_deg: float
    area_sqdeg: float
    log_age_yr: float
    av_mag: float
    pm_ra: float
    pm_dec: float
    parallax_mas: float
    rc_deg: float        # core radius (from Hunt+24 clusters.dat)
    rt_deg: float        # tidal radius (from Hunt+24 clusters.dat)
    all_names: str       # comma-separated literature cross-matches

    @property
    def ra_hours(self) -> float:
        return self.ra_deg / 15.0

    @property
    def is_messier(self) -> bool:
        return bool(_MESSIER_RE.search(self.all_names))

    @property
    def is_ngc_ic(self) -> bool:
        return bool(_NGC_RE.search(self.all_names))

    @property
    def is_well_known(self) -> bool:
        return self.is_messier or self.is_ngc_ic

    def display_name(self) -> str:
        """Pick the most user-recognisable name from ``all_names``.

        Preference order: Messier > NGC/IC > primary ``Name`` field.
        """
        m = _MESSIER_RE.search(self.all_names)
        if m:
            return m.group(0).lstrip(", ").strip()
        n = _NGC_RE.search(self.all_names)
        if n:
            return n.group(0).lstrip(", ").strip()
        return self.name

    def radius_deg(self, mode: str) -> float:
        """Effective radius in degrees for the requested *mode*.

        Parameters
        ----------
        mode : str
            One of ``"core"``, ``"r50"``, or ``"tidal"``.

        Uses the Hunt+24 catalogue columns directly:

        - ``r50``  → ``r50_deg``,
        - ``core`` → ``rc_deg``  (falls back to ``r50_deg / 2`` if missing),
        - ``tidal`` → ``rt_deg`` (falls back to ``sqrt(area / pi)``).
        """
        if mode == "r50":
            return self.r50_deg
        if mode == "core":
            return self.rc_deg if self.rc_deg > 0 else self.r50_deg / 2.0
        if mode == "tidal":
            if self.rt_deg > 0:
                return self.rt_deg
            if self.area_sqdeg > 0:
                return math.sqrt(self.area_sqdeg / math.pi)
            return self.r50_deg
        raise ValueError(f"unknown radius mode: {mode!r}")


def _shortlist_path() -> Path:
    """Resolve the CSV path across source / PyInstaller / Android modes."""
    here = Path(__file__).resolve().parent
    # services/ -> repo root, where the CSV lives next to main.py
    candidates = [
        here.parent / SHORTLIST_FILENAME,
        Path.cwd() / SHORTLIST_FILENAME,
    ]
    if getattr(sys, "frozen", False):
        candidates.append(
            Path(getattr(sys, "_MEIPASS", "")) / "crowdsky_app"
            / SHORTLIST_FILENAME)
        candidates.append(
            Path(getattr(sys, "_MEIPASS", "")) / SHORTLIST_FILENAME)
    if "ANDROID_ARGUMENT" in os.environ:
        candidates.append(here.parent / SHORTLIST_FILENAME)
    for c in candidates:
        if c.is_file():
            return c
    raise FileNotFoundError(
        f"{SHORTLIST_FILENAME} not found. Looked in: "
        + ", ".join(str(c) for c in candidates))


_cache: list[Cluster] | None = None


def load_shortlist() -> list[Cluster]:
    """Read the shortlist CSV once and cache it in memory."""
    global _cache
    if _cache is not None:
        return _cache
    path = _shortlist_path()
    out: list[Cluster] = []
    with path.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            def _f(k: str) -> float:
                v = row.get(k, "")
                return float(v) if v not in ("", None) else 0.0

            out.append(Cluster(
                rank=int(row["rank"]),
                name=row["Name"],
                ra_deg=_f("RA_deg"),
                dec_deg=_f("Dec_deg"),
                glon_deg=_f("GLON_deg"),
                glat_deg=_f("GLAT_deg"),
                dist_pc=_f("dist_pc"),
                n_stars=int(row["N_stars"]),
                r50_pc=_f("r50_pc"),
                r50_deg=_f("r50_deg"),
                area_sqdeg=_f("area_sqdeg"),
                log_age_yr=_f("logAge_yr"),
                av_mag=_f("AV_mag"),
                pm_ra=_f("pmRA_masyr"),
                pm_dec=_f("pmDec_masyr"),
                parallax_mas=_f("parallax_mas"),
                rc_deg=_f("rc_deg"),
                rt_deg=_f("rt_deg"),
                all_names=row.get("all_names", row["Name"]).strip(),
            ))
    _cache = out
    return out


def filter_by_name_class(
    clusters: Iterable[Cluster],
    name_class: str,
) -> list[Cluster]:
    """Filter clusters by name notoriety.

    Parameters
    ----------
    name_class : str
        ``"messier"``, ``"ngc"``, or ``"any"``.  ``messier`` keeps only M*
        names; ``ngc`` keeps M* + NGC/IC; ``any`` keeps everything.
    """
    if name_class == "any":
        return list(clusters)
    if name_class == "messier":
        return [c for c in clusters if c.is_messier]
    if name_class == "ngc":
        return [c for c in clusters if c.is_well_known]
    raise ValueError(f"unknown name_class: {name_class!r}")
