"""Build the bundled ``hunt24_shortlist.csv`` from raw Hunt+24 data.

Inputs (under ``.claude/background_data/``, not bundled):

- ``hunt24_shortlist.csv`` — Kieran's curated shortlist of 306 clusters
  matching the Seestar criteria (0.5 < area < 30 sq.deg, dist < 2 kpc,
  N_stars > 100).  Created from the Hunt+24 master catalogue.
- ``J_A+A_686_A42_clusters.dat.gz.fits`` — full Hunt+24 catalogue
  (Table 1) downloaded from CDS.  Provides ``AllNames`` (literature
  cross-matches) + accurate core / tidal radii.

Output (committed):

- ``<repo>/hunt24_shortlist.csv`` — enriched copy with three extra
  columns: ``rc_deg`` (core radius), ``rt_deg`` (tidal radius), and
  ``all_names`` (comma-separated literature designations).  This is
  what the running app reads via ``services.target_catalogue``.

Re-run after either input changes:

    uv run python scripts/build_hunt_shortlist.py
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

from astropy.io import fits


REPO = Path(__file__).resolve().parent.parent
RAW_DIR = REPO / ".claude" / "background_data"
SHORTLIST_IN = RAW_DIR / "hunt24_shortlist.csv"
FITS_IN = RAW_DIR / "J_A+A_686_A42_clusters.dat.gz.fits"
SHORTLIST_OUT = REPO / "hunt24_shortlist.csv"


def main() -> int:
    if not SHORTLIST_IN.is_file():
        print(f"missing {SHORTLIST_IN}", file=sys.stderr)
        return 1
    if not FITS_IN.is_file():
        print(f"missing {FITS_IN}", file=sys.stderr)
        return 1

    with fits.open(FITS_IN) as hdul:
        data = hdul[1].data
        name_to_idx = {n.strip(): i for i, n in enumerate(data["Name"])}

        rc_arr = data["rc"]
        rt_arr = data["rt"]
        all_arr = data["AllNames"]

    with SHORTLIST_IN.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        in_rows = list(reader)
        in_fields = list(reader.fieldnames or [])

    out_fields = in_fields + ["rc_deg", "rt_deg", "all_names"]
    out_rows: list[dict] = []
    matched = 0
    missing: list[str] = []
    for row in in_rows:
        name = row["Name"]
        idx = name_to_idx.get(name)
        if idx is None:
            missing.append(name)
            row["rc_deg"] = ""
            row["rt_deg"] = ""
            row["all_names"] = name
        else:
            matched += 1
            row["rc_deg"] = f"{float(rc_arr[idx]):.6f}"
            row["rt_deg"] = f"{float(rt_arr[idx]):.6f}"
            # Strip whitespace; AllNames is sometimes padded.
            row["all_names"] = str(all_arr[idx]).strip()
        out_rows.append(row)

    with SHORTLIST_OUT.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=out_fields)
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"matched {matched} / {len(in_rows)} clusters")
    if missing:
        print(f"missing names: {missing[:10]}{'...' if len(missing) > 10 else ''}")
    print(f"wrote {SHORTLIST_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
