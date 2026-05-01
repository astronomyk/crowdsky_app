"""Crawl local directories for Seestar FITS files and classify by stacking status.

Walks a user-selected directory tree looking for raw ``Light_*.fit`` files
(in ``*_sub/`` folders or flat directories), groups them into 15-minute
time blocks, and classifies each block as green (on server), yellow
(pre-stacked locally, not yet uploaded), or red (raw frames needing stacking).
"""

import os
import re
from datetime import datetime
from pathlib import Path

from seestarpy.crowdsky.chunks import (
    CROWDSKY_RE,
    parse_light_filename,
    group_frames_into_blocks,
    parse_coverage_from_filenames,
    compute_chunk_key,
    local_dt_to_chunk_str,
)

# Flexible regex that matches CrowdSky filenames with OR without HEALPix suffix.
# The server's upload_stack.php may return chunk_keys without _HP when RA/Dec
# are missing from the FITS header.
_CROWDSKY_RE_FLEX = re.compile(
    r"^CrowdSky_(\d+)_(.+)_(\d+\.\d+s)_([A-Za-z]+)_(\d{8}\.\d{1,2})(?:_HP(\d{6}))?\.fit$"
)


def _read_local_fits_ra_dec(fits_path):
    """Read RA/Dec from the first two FITS header blocks (5760 bytes).

    Parameters
    ----------
    fits_path : str or Path
        Absolute path to a local ``.fit`` file.

    Returns
    -------
    tuple[float, float] or tuple[None, None]
    """
    try:
        with open(fits_path, "rb") as f:
            header_bytes = f.read(5760).decode("ascii", errors="replace")
        ra = dec = None
        for i in range(0, len(header_bytes), 80):
            card = header_bytes[i : i + 80]
            if card.startswith("RA      ="):
                ra = float(card.split("=")[1].split("/")[0].strip())
            elif card.startswith("DEC     ="):
                dec = float(card.split("=")[1].split("/")[0].strip())
            if ra is not None and dec is not None:
                return (ra, dec)
    except Exception:
        pass
    return (None, None)


def _find_target_dirs(root_path):
    """Find directories containing raw Light_*.fit files.

    Looks for two patterns:
    1. Standard Seestar layout: ``*_sub/`` dirs containing Light frames,
       with a sibling dir (same name minus ``_sub``) for stacked output.
    2. Flat directories: any dir containing Light_*.fit files directly.

    Returns
    -------
    list[dict]
        Each dict has keys:
        - ``target_name`` (str): inferred target name
        - ``raw_dir`` (Path): directory containing raw Light_*.fit files
        - ``stacked_dir`` (Path or None): sibling dir for stacked output
        - ``base_path`` (str): parent path for grouping in the UI
    """
    root = Path(root_path)
    results = []
    seen_raw_dirs = set()

    for dirpath, dirnames, filenames in os.walk(root):
        dirpath = Path(dirpath)
        dirname = dirpath.name

        # Check if any Light_*.fit files exist here
        has_light = any(f.startswith("Light_") and f.endswith(".fit")
                        for f in filenames)
        if not has_light:
            continue

        if dirpath in seen_raw_dirs:
            continue
        seen_raw_dirs.add(dirpath)

        # Determine target name and stacked sibling
        if dirname.endswith("_sub"):
            target_name = dirname[:-4]
            stacked_dir = dirpath.parent / target_name
            if not stacked_dir.is_dir():
                stacked_dir = None
        else:
            target_name = dirname
            stacked_dir = None

        results.append({
            "target_name": target_name,
            "raw_dir": dirpath,
            "stacked_dir": stacked_dir,
            "base_path": str(dirpath.parent),
        })

    results.sort(key=lambda d: (d["base_path"], d["target_name"]))
    return results


def crawl_directory(root_path, server_chunk_keys=None, on_progress=None):
    """Walk a directory tree and classify Seestar data by stacking status.

    Parameters
    ----------
    root_path : str or Path
        User-selected root directory (e.g. Seestar SD card or backup).
    server_chunk_keys : set[str] or None
        Chunk keys already on the CrowdSky server.  Used to identify
        green (already uploaded) blocks.  If ``None``, no green
        classification is performed.
    on_progress : callable or None
        Called as ``on_progress(current_idx, total_targets, target_name)``
        after processing each target.

    Returns
    -------
    dict
        Keyed by ``(base_path, target_name)`` tuples.  Values are dicts:

        - ``"green"`` — list of chunk_key strings already on the server
        - ``"yellow"`` — list of ``(filepath, chunk_key)`` tuples for
          pre-stacked CrowdSky files ready to upload
        - ``"red"`` — list of block dicts (from
          :func:`group_frames_into_blocks`) with extra keys
          ``"chunk_key"`` and ``"full_paths"``
    """
    if server_chunk_keys is None:
        server_chunk_keys = set()

    target_dirs = _find_target_dirs(root_path)
    results = {}

    for idx, tdir in enumerate(target_dirs):
        target_name = tdir["target_name"]
        raw_dir = tdir["raw_dir"]
        stacked_dir = tdir["stacked_dir"]
        base_path = tdir["base_path"]

        if on_progress:
            on_progress(idx, len(target_dirs), target_name)

        # Parse raw Light_*.fit filenames
        parsed = []
        for fname in os.listdir(raw_dir):
            info = parse_light_filename(fname)
            if info:
                info["filename"] = fname
                info["full_path"] = str(raw_dir / fname)
                parsed.append(info)

        if not parsed:
            continue

        # Group into 15-minute blocks
        blocks = group_frames_into_blocks(parsed)

        # Skip incomplete (current) blocks
        now = datetime.now()
        blocks = {k: v for k, v in blocks.items() if v["block_end"] <= now}
        if not blocks:
            continue

        # Attach full_paths and chunk_key to each block
        # Build a mapping from filename -> full_path
        path_lookup = {p["filename"]: p["full_path"] for p in parsed}
        for block in blocks.values():
            block["full_paths"] = [path_lookup[f] for f in block["files"]]
            # Read RA/Dec from first file to compute chunk key
            ra, dec = _read_local_fits_ra_dec(block["full_paths"][0])
            block["chunk_key"] = compute_chunk_key(
                block["block_start"], ra, dec
            )

        # Collect local CrowdSky_* coverage from stacked sibling dir
        local_crowdsky = []
        local_crowdsky_paths = {}  # fname -> full path
        if stacked_dir and stacked_dir.is_dir():
            for f in os.listdir(stacked_dir):
                if f.startswith("CrowdSky_"):
                    local_crowdsky.append(f)
                    local_crowdsky_paths[f] = str(stacked_dir / f)

        # Also check .crowdsky/stacks/<target>/ cache directories.
        # Check both the crawl root and the target's base_path (parent of
        # raw dir), since the user may crawl either level.
        cache_search_dirs = set()
        cache_search_dirs.add(Path(root_path) / ".crowdsky" / "stacks" / target_name)
        cache_search_dirs.add(Path(base_path) / ".crowdsky" / "stacks" / target_name)
        for cache_dir in cache_search_dirs:
            if cache_dir.is_dir():
                for f in os.listdir(cache_dir):
                    if f.startswith("CrowdSky_") and f not in local_crowdsky_paths:
                        local_crowdsky.append(f)
                        local_crowdsky_paths[f] = str(cache_dir / f)

        # Build coverage set: (chunk_str, exposure, filter) tuples.
        # Use flexible regex to handle files without _HP suffix.
        local_coverage = parse_coverage_from_filenames(local_crowdsky)
        for fname in local_crowdsky:
            m = _CROWDSKY_RE_FLEX.match(fname)
            if m and not CROWDSKY_RE.match(fname):
                # File matched flex but not strict — add to coverage manually
                local_coverage.add((m.group(5), m.group(3), m.group(4)))

        # Also parse chunk_keys from local CrowdSky files (for yellow).
        # Use flexible regex to handle files with or without _HP<pixel>.
        local_crowdsky_by_chunk = {}
        for fname in local_crowdsky:
            m = _CROWDSKY_RE_FLEX.match(fname)
            if m:
                chunk_str = m.group(5)
                hp = m.group(6)
                # Build chunk_key matching the format used by server_chunk_keys
                ck = f"{chunk_str}_HP{hp}" if hp else chunk_str
                local_crowdsky_by_chunk[ck] = local_crowdsky_paths.get(
                    fname, fname)

        # Classify blocks
        green_set = set()
        yellow = []
        red = []

        # Yellow: local CrowdSky files not yet on server
        for chunk_key, filepath in local_crowdsky_by_chunk.items():
            if chunk_key in server_chunk_keys:
                green_set.add(chunk_key)
            else:
                yellow.append((filepath, chunk_key))

        # Green from server: blocks whose chunk_key is already on server
        # Red: blocks not covered locally or on server
        for block in blocks.values():
            ck = block["chunk_key"]
            chunk_str = local_dt_to_chunk_str(block["block_start"])
            coverage_tuple = (chunk_str, block["exposure"], block["filter"])

            if ck in server_chunk_keys:
                green_set.add(ck)
            elif coverage_tuple in local_coverage:
                # Covered by a local CrowdSky file (already handled in yellow)
                pass
            else:
                red.append(block)

        key = (base_path, target_name)
        results[key] = {
            "green": sorted(green_set),
            "yellow": yellow,
            "red": red,
        }

    if on_progress:
        on_progress(len(target_dirs), len(target_dirs), "Done")

    return results
