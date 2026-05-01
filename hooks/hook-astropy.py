"""Custom astropy hook — only bundle submodules used by CrowdSky.

Overrides the default hook-astropy.py from pyinstaller-hooks-contrib,
which calls collect_submodules('astropy') and crashes when
astropy.visualization.wcsaxes tries pytest.importorskip('matplotlib').
"""

from PyInstaller.utils.hooks import collect_data_files

# Only the submodules we actually need
hiddenimports = [
    'astropy.io',
    'astropy.io.fits',
    'astropy.io.fits.card',
    'astropy.io.fits.column',
    'astropy.io.fits.connect',
    'astropy.io.fits.convenience',
    'astropy.io.fits.diff',
    'astropy.io.fits.file',
    'astropy.io.fits.fitsrec',
    'astropy.io.fits.hdu',
    'astropy.io.fits.hdu.base',
    'astropy.io.fits.hdu.compressed',
    'astropy.io.fits.hdu.groups',
    'astropy.io.fits.hdu.hdulist',
    'astropy.io.fits.hdu.image',
    'astropy.io.fits.hdu.nonstandard',
    'astropy.io.fits.hdu.streaming',
    'astropy.io.fits.hdu.table',
    'astropy.io.fits.header',
    'astropy.io.fits.util',
    'astropy.io.fits.verify',
    'astropy.table',
    'astropy.units',
    'astropy.utils',
    'astropy.utils.data',
    'astropy.utils.iers',
    'astropy.config',
    'astropy.extern',
    'astropy.extern.configobj',
    'astropy.extern.configobj.configobj',
    'astropy.extern.configobj.validate',
]

# Astropy needs its data files (e.g., IERS tables, unit definitions)
datas = collect_data_files('astropy')
