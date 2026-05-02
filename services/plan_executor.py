"""Push a planned observation list to a Seestar.

Wraps :func:`seestarpy.plan.set_view_plan` with our own
``set_active_seestar`` / connection plumbing so the call hits the
currently selected device.
"""

from __future__ import annotations

from seestarpy import plan as _plan

from .plan_builder import to_seestar_payload
from .seestar_service import set_active_seestar


def push_plan(ip: str, plan: dict) -> dict:
    """Send *plan* to the Seestar at *ip* and start it.

    Parameters
    ----------
    ip : str
        IP address of the Seestar (set as connection.DEFAULT_IP for the
        duration of the call).
    plan : dict
        Output of :func:`plan_builder.build_plan`.  Local-only fields
        (``summary``, ``lat``, …) are stripped before sending.

    Returns
    -------
    dict
        Raw JSON-RPC response from the device.
    """
    set_active_seestar(ip)
    payload = to_seestar_payload(plan)
    return _plan.set_view_plan(payload)


def stop_plan(ip: str) -> dict:
    set_active_seestar(ip)
    return _plan.stop_view_plan()


def get_seestar_location(ip: str) -> tuple[float, float] | None:
    """Read (lat, lon) from the Seestar.  Returns None on failure.

    The device returns ``result`` as ``[lon, lat]`` despite the seestarpy
    docstring saying otherwise — verified against Vienna coordinates
    (`[14.79, 47.95]` ↔ lat 48.2°N, lon 16.4°E in Austria).  When one
    value is outside [-90, 90] we use that to disambiguate.
    """
    set_active_seestar(ip)
    try:
        from seestarpy import raw
        resp = raw.get_user_location()
        result = resp.get("result") if isinstance(resp, dict) else None
        if isinstance(result, dict):
            lat = result.get("lat") or result.get("latitude")
            lon = result.get("lon") or result.get("longitude")
            if lat is not None and lon is not None:
                return float(lat), float(lon)
            return None
        if isinstance(result, (list, tuple)) and len(result) >= 2:
            a, b = float(result[0]), float(result[1])
            # Disambiguate: lat must be in [-90, 90].
            if abs(a) > 90 and abs(b) <= 90:
                return b, a    # (lat, lon)
            if abs(b) > 90 and abs(a) <= 90:
                return a, b
            # Both in [-90, 90] — trust seestarpy's observed [lon, lat] order.
            return b, a
    except Exception:
        return None
    return None
