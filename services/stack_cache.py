"""Persistent cache for locally stacked FITS files.

After a successful upload, stacked files are moved from the temp
directory to ``<crawl_root>/.crowdsky/stacks/<target>/`` using the
CrowdSky naming convention.  This lets the user inspect results and
allows the crawler to recognize them as covered blocks.
"""

import shutil
from pathlib import Path


def get_cache_dir(base_path):
    """Return the cache directory for a given crawl root.

    Parameters
    ----------
    base_path : str or Path
        The top-level directory the user selected for crawling.

    Returns
    -------
    Path
        ``<base_path>/.crowdsky/stacks/``
    """
    return Path(base_path) / ".crowdsky" / "stacks"


def move_to_cache(fits_path, thumb_path, target_name, chunk_key,
                  base_path, metadata=None):
    """Move stacked FITS + thumbnail to persistent cache.

    Files are renamed to the CrowdSky naming convention so the crawler
    recognizes them as covered blocks.

    Parameters
    ----------
    fits_path : Path
        Temporary stacked FITS file.
    thumb_path : Path or None
        Temporary thumbnail PNG.
    target_name : str
        Observation target, e.g. ``"M 7"``.
    chunk_key : str
        e.g. ``"20250731.79_HP154750"``.
    base_path : str
        The crawl root (used to locate the cache directory).
    metadata : dict or None
        Stacking metadata with keys like ``n_frames_input``,
        ``filter``, ``total_exptime``.
    """
    metadata = metadata or {}
    fits_path = Path(fits_path)
    if not fits_path.exists():
        return

    target_dir = get_cache_dir(base_path) / target_name
    target_dir.mkdir(parents=True, exist_ok=True)

    # Build CrowdSky filename
    n_frames = metadata.get("n_frames_aligned") or metadata.get("n_frames_input") or 0
    exptime = metadata.get("total_exptime") or 0
    n_input = metadata.get("n_frames_input") or 1
    per_frame = exptime / n_input if n_input else 0
    exposure_str = f"{per_frame:.1f}s"
    filter_name = metadata.get("filter") or "IRCUT"

    stem = f"CrowdSky_{n_frames}_{target_name}_{exposure_str}_{filter_name}_{chunk_key}"

    dest_fits = target_dir / f"{stem}.fit"
    dest_thumb = target_dir / f"{stem}_thumb.png"

    try:
        shutil.move(str(fits_path), str(dest_fits))
    except Exception:
        # Fall back to copy if move fails (e.g. cross-device)
        try:
            shutil.copy2(str(fits_path), str(dest_fits))
        except Exception:
            return

    if thumb_path and Path(thumb_path).exists():
        try:
            shutil.move(str(thumb_path), str(dest_thumb))
        except Exception:
            try:
                shutil.copy2(str(thumb_path), str(dest_thumb))
            except Exception:
                pass
