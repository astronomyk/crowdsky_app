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

# Names that look like Messier or NGC entries.  The shortlist is dominated
# by HSC_/Theia_/OCSN_ designations, so a name match is a useful proxy
# for "well known".
_MESSIER_RE = re.compile(r"^(M|Messier)[\s_]*\d+", re.IGNORECASE)
_NGC_RE = re.compile(r"^(NGC|IC)[\s_]*\d+", re.IGNORECASE)


@dataclass(frozen=True)
class Cluster:
    """One row of the Hunt+24 shortlist."""
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

    @property
    def ra_hours(self) -> float:
        return self.ra_deg / 15.0

    @property
    def is_messier(self) -> bool:
        return bool(_MESSIER_RE.match(self.name))

    @property
    def is_ngc_ic(self) -> bool:
        return bool(_NGC_RE.match(self.name))

    @property
    def is_well_known(self) -> bool:
        return self.is_messier or self.is_ngc_ic

    def radius_deg(self, mode: str) -> float:
        """Effective radius in degrees for the requested *mode*.

        Parameters
        ----------
        mode : str
            One of ``"core"``, ``"r50"``, or ``"tidal"``.

        The shortlist only carries ``r50_deg`` and ``area_sqdeg``, so:

        - ``r50``  → ``r50_deg`` directly,
        - ``core`` → ``r50_deg / 2`` (rough),
        - ``tidal`` → ``sqrt(area_sqdeg / pi)``.
        """
        if mode == "r50":
            return self.r50_deg
        if mode == "core":
            return self.r50_deg / 2.0
        if mode == "tidal":
            if self.area_sqdeg <= 0:
                return self.r50_deg
            return math.sqrt(self.area_sqdeg / math.pi)
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
            out.append(Cluster(
                rank=int(row["rank"]),
                name=row["Name"],
                ra_deg=float(row["RA_deg"]),
                dec_deg=float(row["Dec_deg"]),
                glon_deg=float(row["GLON_deg"]),
                glat_deg=float(row["GLAT_deg"]),
                dist_pc=float(row["dist_pc"]),
                n_stars=int(row["N_stars"]),
                r50_pc=float(row["r50_pc"]),
                r50_deg=float(row["r50_deg"]),
                area_sqdeg=float(row["area_sqdeg"]),
                log_age_yr=float(row["logAge_yr"]),
                av_mag=float(row["AV_mag"]),
                pm_ra=float(row["pmRA_masyr"]),
                pm_dec=float(row["pmDec_masyr"]),
                parallax_mas=float(row["parallax_mas"]),
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
