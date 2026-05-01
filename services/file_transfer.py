"""Download files from a Seestar via HTTP."""

import tempfile
from pathlib import Path

from seestarpy import data
from .seestar_service import set_active_seestar


def download_from_seestar(folder, filename, ip):
    """Download a file from the Seestar via HTTP (port 80).

    Delegates to ``seestarpy.data.download_file``.

    Parameters
    ----------
    folder : str
        Folder under MyWorks, e.g. ``"Aur_1_02"``.
    filename : str
        File name within the folder.
    ip : str
        Seestar IP address.

    Returns
    -------
    Path
        The local path of the downloaded file.
    """
    tmp = get_temp_dir()
    set_active_seestar(ip)
    local_path = data.download_file(folder, filename, dest=str(tmp))
    return Path(local_path)


def get_temp_dir():
    """Return a temp directory for downloaded files."""
    tmp = Path(tempfile.gettempdir()) / "crowdsky_app"
    tmp.mkdir(parents=True, exist_ok=True)
    return tmp
