"""Local PC stacking using crowdsky's FrameCollection.

Wraps the stacking engine for use in the Kivy app, with no dependency
on the ``worker/`` directory.  Produces a multi-extension FITS and a
PNG thumbnail, and returns metadata needed for the upload API.
"""

from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image
from astropy.io import fits
from crowdsky.stacking import FrameCollection


def stack_local_block(fits_paths, output_dir, on_progress=None):
    """Stack raw FITS files locally using FrameCollection.

    Parameters
    ----------
    fits_paths : list[str | Path]
        Absolute paths to raw Light_*.fit files.
    output_dir : str or Path
        Directory to write output files.
    on_progress : callable or None
        Called as ``on_progress(phase, detail)`` where *phase* is one of
        ``"loading"``, ``"stacking"``, ``"saving"``, ``"thumbnail"``.

    Returns
    -------
    dict
        Keys: ``fits_path``, ``thumbnail_path``, ``n_frames_input``,
        ``n_frames_aligned``, ``total_exptime``, ``ra``, ``dec``,
        ``date_obs_start``, ``date_obs_end``, ``filter``.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if on_progress:
        on_progress("loading", f"{len(fits_paths)} frames")

    fc = FrameCollection(fits_paths)

    if on_progress:
        on_progress("stacking", "aligning and stacking")

    fc.process(method="mean", sigma_clip=3.0, detect_stars=True)

    fits_out = output_dir / "stacked.fits"

    if on_progress:
        on_progress("saving", str(fits_out))

    fc.save(str(fits_out))

    metadata = _extract_metadata(fc)

    if on_progress:
        on_progress("thumbnail", "generating")

    thumb_out = output_dir / "stacked_thumb.png"
    _generate_thumbnail(fits_out, thumb_out)

    return {
        "fits_path": fits_out,
        "thumbnail_path": thumb_out,
        **metadata,
    }


def _extract_metadata(fc):
    """Pull aggregated metadata from FrameCollection after processing.

    Mirrors the metadata extraction in ``worker/stacking_adapter.py``.
    """
    exptimes = []
    date_obs_values = []
    ra_values = []
    dec_values = []
    filter_values = []

    for frame in fc.frames:
        hdr = frame.hdu.header if hasattr(frame, "hdu") and frame.hdu else None
        if hdr is None:
            continue
        if "EXPTIME" in hdr:
            exptimes.append(float(hdr["EXPTIME"]))
        if "DATE-OBS" in hdr:
            date_obs_values.append(str(hdr["DATE-OBS"]))
        if "RA" in hdr:
            ra_values.append(float(hdr["RA"]))
        if "DEC" in hdr:
            dec_values.append(float(hdr["DEC"]))
        if "FILTER" in hdr:
            filter_values.append(str(hdr["FILTER"]))

    return {
        "n_frames_input": fc.n_frames,
        "n_frames_aligned": fc.n_aligned,
        "total_exptime": sum(exptimes) if exptimes else None,
        "date_obs_start": min(date_obs_values) if date_obs_values else None,
        "date_obs_end": max(date_obs_values) if date_obs_values else None,
        "ra": (sum(ra_values) / len(ra_values)) if ra_values else None,
        "dec": (sum(dec_values) / len(dec_values)) if dec_values else None,
        "filter": (Counter(filter_values).most_common(1)[0][0]
                   if filter_values else None),
    }


def _generate_thumbnail(fits_path, output_path, max_size=512):
    """Create a PNG thumbnail from a multi-extension stacked FITS.

    Handles both multi-extension (RED/GREEN/BLUE) and single-plane FITS.
    Uses 1st/99.5th percentile stretch per channel.
    """
    with fits.open(fits_path) as hdul:
        if "RED" in hdul and "GREEN" in hdul and "BLUE" in hdul:
            r = hdul["RED"].data
            g = hdul["GREEN"].data
            b = hdul["BLUE"].data
            rgb = np.stack([r, g, b], axis=-1)
        else:
            data = hdul[0].data
            if data is None:
                raise ValueError(f"No data in primary HDU of {fits_path}")
            if data.ndim == 3 and data.shape[0] == 3:
                rgb = np.transpose(data, (1, 2, 0))
            elif data.ndim == 3 and data.shape[2] == 3:
                rgb = data
            elif data.ndim == 2:
                rgb = np.stack([data, data, data], axis=-1)
            else:
                raise ValueError(f"Unexpected data shape: {data.shape}")

    rgb = rgb.astype(np.float64)
    for ch in range(rgb.shape[2]):
        plane = rgb[:, :, ch]
        vmin, vmax = np.percentile(plane, [1, 99.5])
        if vmax > vmin:
            rgb[:, :, ch] = (plane - vmin) / (vmax - vmin) * 255
        else:
            rgb[:, :, ch] = 0
    rgb = np.clip(rgb, 0, 255).astype(np.uint8)

    img = Image.fromarray(rgb)
    w, h = img.size
    scale = max_size / max(w, h)
    if scale < 1:
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, "PNG")
