"""Thin wrapper around seestarpy.crowdsky.server for the app."""

from seestarpy.crowdsky import server


def validate_credentials(username, password):
    """Test credentials against the CrowdSky server.

    Returns True on success, raises RuntimeError on 401.
    """
    server.set_credentials(username, password)
    server.list_stacks()  # 401 -> RuntimeError
    return True


def get_my_stacks():
    """Return list of user's stacks (uses previously set credentials)."""
    return server.list_stacks()


def get_server_stacks_by_object():
    """Return dict mapping object_name -> list of server stack dicts."""
    stacks = get_my_stacks()
    by_object = {}
    for s in stacks:
        name = s.get("object_name", "")
        by_object.setdefault(name, []).append(s)
    return by_object


def get_server_chunk_keys():
    """Return set of chunk_keys already on the server."""
    stacks = get_my_stacks()
    return {s["chunk_key"] for s in stacks if s.get("chunk_key")}


def fetch_thumbnail(stack_id: int) -> bytes:
    """Fetch thumbnail PNG bytes for a given stack ID."""
    resp = server._request(
        "GET", "/api/thumbnail.php", params={"id": stack_id}, timeout=15)
    return resp.content


def upload(fits_path, thumbnail=None, n_frames_input=None,
           n_frames_aligned=None, date_obs_start=None, date_obs_end=None,
           scrub_location=None):
    """Upload a stacked FITS to CrowdSky."""
    return server.upload_stack(
        fits_path,
        thumbnail=thumbnail,
        n_frames_input=n_frames_input,
        n_frames_aligned=n_frames_aligned,
        date_obs_start=date_obs_start,
        date_obs_end=date_obs_end,
        scrub_location=scrub_location,
    )
