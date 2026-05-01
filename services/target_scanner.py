"""Scan Seestars and classify targets into green/yellow/red status.

Green  = chunk_key already on CrowdSky server (nothing to do)
Yellow = CrowdSky_* stacked file on Seestar, not yet uploaded
Red    = raw frames in a time block, not yet stacked
"""

from seestarpy import connection, data
from seestarpy.crowdsky.chunks import (
    CROWDSKY_RE, CROWDSKY_RE_LEGACY, local_dt_to_chunk_str,
    find_unstacked_blocks,
)
from datetime import datetime

from .seestar_service import set_active_seestar, list_targets


def scan_seestar(ip, server_chunk_keys, on_progress=None):
    """Scan one Seestar and classify all targets' blocks.

    Parameters
    ----------
    ip : str
        Seestar IP address.
    server_chunk_keys : set[str]
        Chunk keys already on the CrowdSky server.
    on_progress : callable, optional
        Called with (current_index, total_targets, target_name) as scanning proceeds.

    Returns
    -------
    dict
        {target_name: {"green": [...], "yellow": [...], "red": [...]}}
    """
    set_active_seestar(ip)
    result = {}

    try:
        targets = list_targets()
    except Exception:
        return result

    # Deduplicate targets to get accurate total
    seen_targets = set()
    unique_targets = []
    for t in targets:
        name = t["target"]
        if name not in seen_targets:
            seen_targets.add(name)
            unique_targets.append(name)

    total = len(unique_targets)
    for idx, target_name in enumerate(unique_targets):
        if on_progress:
            on_progress(idx, total, target_name)

        green = []
        yellow = []
        red = []

        # Scan for CrowdSky_* files (pre-stacked) in the target folder
        try:
            crowdsky_files = _list_crowdsky_files(target_name)
        except Exception:
            crowdsky_files = []

        for fname, chunk_key in crowdsky_files:
            if chunk_key in server_chunk_keys:
                green.append(chunk_key)
            else:
                yellow.append((fname, chunk_key))

        # Scan for raw unstacked blocks
        try:
            blocks = find_unstacked_blocks(target_name)
        except Exception:
            blocks = []

        for block in blocks:
            red.append(block)

        result[target_name] = {
            "green": green,
            "yellow": yellow,
            "red": red,
        }

    return result


def scan_all_seestars(seestars, server_chunk_keys, on_progress=None):
    """Scan all Seestars sequentially.

    Parameters
    ----------
    seestars : dict
        {hostname: ip} mapping of discovered Seestars.
    server_chunk_keys : set[str]
        Chunk keys already on the CrowdSky server.
    on_progress : callable, optional
        Called with (current_index, total_targets, target_name) as scanning proceeds.
        Index counts across all Seestars.

    Returns
    -------
    dict
        {(ip, target_name): {"green": [...], "yellow": [...], "red": [...]}}
    """
    all_results = {}
    seen_ips = set()
    # Track cumulative offset across multiple Seestars
    offset = [0]

    def _relay_progress(idx, total, target_name):
        if on_progress:
            on_progress(offset[0] + idx, offset[0] + total, target_name)

    for hostname, ip in seestars.items():
        if ip in seen_ips:
            continue
        seen_ips.add(ip)

        seestar_result = scan_seestar(ip, server_chunk_keys, on_progress=_relay_progress)
        # Update offset after each Seestar (use actual targets found)
        offset[0] += len(seestar_result)
        for target_name, status in seestar_result.items():
            all_results[(ip, target_name)] = status

    return all_results


def get_device_info(ip):
    """Get serial number and product model for a Seestar.

    Returns (serial_number, product_model).
    """
    set_active_seestar(ip)
    try:
        params = {"method": "get_device_state",
                  "params": {"keys": ["device"]}}
        resp = connection.send_command(params)
        dev = resp.get("result", {}).get("device", {})
        return dev.get("sn", ""), dev.get("product_model", "")
    except Exception:
        return "", ""


def _list_crowdsky_files(target_name):
    """List CrowdSky_* files in a target folder on the active Seestar.

    Matches both new-format (with HEALPix pixel) and legacy-format
    (with local timestamp) CrowdSky filenames.

    For legacy files, a chunk_key is synthesized from the embedded
    timestamp using the same UTC conversion as find_unstacked_blocks.

    Uses ``seestarpy.data.list_folder_contents()`` (JSON-RPC, no SMB).

    Returns list of (filename, chunk_key) tuples.
    """
    files = data.list_folder_contents(target_name)

    results = []
    for name in files:
        if not name.startswith("CrowdSky_"):
            continue

        # Try new format: CrowdSky_<N>_<target>_<exp>_<filter>_<YYYYMMDD.CC>_HP<nnnnnn>.fit
        m = CROWDSKY_RE.match(name)
        if m:
            chunk_key = f"{m.group(5)}_HP{m.group(6)}"
            results.append((name, chunk_key))
            continue

        # Try legacy format: CrowdSky_<N>_<target>_<exp>_<filter>_<YYYYMMDD-HHMMSS>.fit
        m = CROWDSKY_RE_LEGACY.match(name)
        if m:
            dt = datetime.strptime(m.group(5), "%Y%m%d-%H%M%S")
            chunk_str = local_dt_to_chunk_str(dt)
            # Legacy files have no HEALPix pixel — use chunk_str alone
            chunk_key = chunk_str
            results.append((name, chunk_key))

    return results
