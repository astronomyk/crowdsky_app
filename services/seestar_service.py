"""Wraps seestarpy connection and discovery calls.

All JSON-RPC calls use ``connection.send_command`` directly, bypassing the
``@multiple_ips`` decorator that wraps the ``raw.*`` / ``data.*`` public API.
This ensures each call only talks to the currently active Seestar (set via
``set_active_seestar``) without touching stale IPs in ``AVAILABLE_IPS``.
"""

import socket

from seestarpy import connection
from seestarpy.crowdsky import chunks


def find_seestars(n=5, timeout=2):
    """Scan the network for up to *n* Seestars.

    Returns dict of {hostname: ip}.
    """
    connection.find_available_ips(n, timeout=timeout)
    return dict(connection.AVAILABLE_IPS)


def test_connection(ip, port=4700, timeout=2):
    """Test if a Seestar is reachable at the given IP."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((ip, port))
        s.close()
        return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def add_manual_ip(ip, hostname=None):
    """Add a manually specified IP to the available pool."""
    if hostname is None:
        hostname = f"manual-{ip}"
    connection.AVAILABLE_IPS[hostname] = ip
    return {hostname: ip}


def set_active_seestar(ip):
    """Set the global DEFAULT_IP for seestarpy calls."""
    connection.DEFAULT_IP = ip


def get_serial_number():
    """Return the serial number of the currently active Seestar."""
    params = {"method": "get_device_state", "params": {"keys": ["device"]}}
    response = connection.send_command(params)
    result = response.get("result", {})
    return result.get("device", {}).get("sn", "")


def list_targets():
    """List targets on the currently active Seestar."""
    params = {"method": "get_albums"}
    response = connection.send_command(params)

    folders = {}
    for group in response.get("result", {}).get("list", []):
        for entry in group.get("files", []):
            folders[entry["name"]] = entry["count"]

    targets = []
    for name, count in folders.items():
        if name.endswith("_sub"):
            target = name[:-4]
            if target in folders:
                targets.append({
                    "target": target,
                    "raw_files": count,
                    "stacked_files": folders[target],
                })

    targets.sort(key=lambda t: t["target"])
    return targets


def find_unstacked_blocks(target, block_minutes=15):
    """Find unstacked time blocks for a target."""
    return chunks.find_unstacked_blocks(target, block_minutes)
