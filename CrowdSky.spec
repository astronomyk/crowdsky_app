# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for CrowdSky desktop app v3.

Build:
    cd crowdsky_app
    pyinstaller CrowdSky.spec --noconfirm

Output:
    dist/CrowdSky-{version}.exe   (Windows, --onefile mode)
    dist/CrowdSky-{version}       (macOS,   --onefile mode)
"""

import os
import re
import sys
from PyInstaller.utils.hooks import collect_data_files

IS_WINDOWS = sys.platform == 'win32'

if IS_WINDOWS:
    from PyInstaller.utils.win32.versioninfo import (
        VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable,
        StringStruct, VarFileInfo, VarStruct,
    )

block_cipher = None

# Read version from __init__.py
with open('__init__.py') as f:
    VERSION = re.search(r'__version__\s*=\s*["\']([^"\']+)', f.read()).group(1)

if IS_WINDOWS:
    _v = [int(x) for x in VERSION.split('.')]
    while len(_v) < 4:
        _v.append(0)
    WIN_VERSION = tuple(_v[:4])

# Collect Kivy data files (SDL2 binaries, fonts, etc.)
kivy_datas = collect_data_files('kivy')

a = Analysis(
    ['main.py'],
    pathex=[os.path.abspath('.')],
    binaries=[],
    datas=[
        ('crowdsky.kv', 'crowdsky_app'),
        ('hunt24_shortlist.csv', 'crowdsky_app'),
    ] + kivy_datas,
    hiddenimports=[
        # Vendored seestarpy
        'seestarpy',
        'seestarpy.connection',
        'seestarpy.raw',
        'seestarpy.data',
        'seestarpy.stack',
        'seestarpy.ui',
        'seestarpy.status',
        'seestarpy.plan',
        'seestarpy.stream',
        'seestarpy.crowdsky',
        'seestarpy.crowdsky.server',
        'seestarpy.crowdsky.chunks',
        'seestarpy.crowdsky.healpix',
        'seestarpy.events',
        'seestarpy.events.event_listener',
        'seestarpy.events.event_definitions',
        'seestarpy.events.event_stream',
        'seestarpy.events.event_watcher',
        'seestarpy.dashboards',
        # Stacking library (crowdsky package)
        'crowdsky',
        'crowdsky.stacking',
        'crowdsky.stacking.stacking',
        'crowdsky.stacking.fits_header_utils',
        'crowdsky.plate_solver',
        'crowdsky.plate_solver.solver',
        'crowdsky.plate_solver.triangles',
        'crowdsky.plate_solver.catalogue',
        # Stacking dependencies (needed by local_stacker + FrameCollection)
        'numpy',
        'cv2',
        'astropy',
        'astropy.io',
        'astropy.io.fits',
        'astropy.table',
        'astropy.coordinates',
        'astropy.time',
        'astropy.units',
        'erfa',
        'astroalign',
        'PIL',
        'PIL.Image',
        'sep_pjw',
        'sep',
        # App modules
        'crowdsky_app',
        'crowdsky_app.app_state',
        'crowdsky_app.screens',
        'crowdsky_app.screens.login_screen',
        'crowdsky_app.screens.home_screen',
        'crowdsky_app.screens.skymap_screen',
        'crowdsky_app.screens.gallery_screen',
        'crowdsky_app.screens.donate_seestar_screen',
        'crowdsky_app.screens.donate_harddrive_screen',
        'crowdsky_app.screens.plan_screen',
        'crowdsky_app.screens.plan_result_screen',
        'crowdsky_app.screens.status_screen',
        'crowdsky_app.services',
        'crowdsky_app.services.crowdsky_client',
        'crowdsky_app.services.credential_store',
        'crowdsky_app.services.file_transfer',
        'crowdsky_app.services.harddrive_crawler',
        'crowdsky_app.services.job_broker',
        'crowdsky_app.services.local_stacker',
        'crowdsky_app.services.plan_builder',
        'crowdsky_app.services.plan_executor',
        'crowdsky_app.services.seestar_service',
        'crowdsky_app.services.stack_cache',
        'crowdsky_app.services.target_catalogue',
        'crowdsky_app.services.target_scanner',
        'crowdsky_app.services.target_source',
        'crowdsky_app.services.upload_journal',
        'crowdsky_app.widgets',
        'crowdsky_app.widgets.filter_bar',
        'crowdsky_app.widgets.gallery_card',
        'crowdsky_app.widgets.horizon_compass',
        'crowdsky_app.widgets.pagination_bar',
        'crowdsky_app.widgets.plan_skymap',
        'crowdsky_app.widgets.sky_map',
        'crowdsky_app.widgets.timeline',
        'crowdsky_app.widgets.album_row',
        'crowdsky_app.widgets.donate_harddrive_card',
        'crowdsky_app.widgets.donate_seestar_card',
        'crowdsky_app.widgets.job_list_item',
        'crowdsky_app.widgets.thumbnail_popup',
    ],
    hookspath=[os.path.join(os.path.abspath('.'), 'hooks')],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # matplotlib, scipy not used by the app
        'matplotlib', 'matplotlib.pyplot',
        'scipy',
        # Trim astropy to just io.fits + table (skip visualization, cosmology, etc.)
        'astropy.visualization',
        'astropy.cosmology',
        'astropy.modeling',
        'astropy.convolution',
        # Dev/build tools
        'setuptools', 'pip', 'wheel',
        # Unused stdlib modules
        'tkinter', '_tkinter',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

_exe_kwargs = dict(
    name=f'CrowdSky-{VERSION}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    onefile=True,
)

if IS_WINDOWS:
    _exe_kwargs['version'] = VSVersionInfo(
        ffi=FixedFileInfo(
            filevers=WIN_VERSION,
            prodvers=WIN_VERSION,
        ),
        kids=[
            StringFileInfo([StringTable('040904B0', [
                StringStruct('CompanyName', 'University of Vienna'),
                StringStruct('FileDescription', 'CrowdSky - Seestar Cloud Stacking'),
                StringStruct('FileVersion', VERSION),
                StringStruct('ProductName', 'CrowdSky'),
                StringStruct('ProductVersion', VERSION),
            ])]),
            VarFileInfo([VarStruct('Translation', [1033, 1200])]),
        ],
    )

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    **_exe_kwargs,
)
