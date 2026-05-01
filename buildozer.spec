[app]

# (str) Title of your application
title = CrowdSky

# (str) Package name
package.name = crowdsky

# (str) Package domain (needed for android/ios packaging)
package.domain = at.ac.univie

# (str) Source code where the main.py live
source.dir = .

# (list) Source files to include (let empty to include all the files)
source.include_exts = py,kv,png,jpg,json

# (list) List of directory to exclude (let empty to not excluding anything)
source.exclude_dirs = build,dist,plans,screens_layouts,__pycache__,.buildozer,bin,tests,docs

# (list) List of exclusions using pattern matching
source.exclude_patterns = *.spec,buildozer.spec

# (str) Application versioning — read from __init__.py (single source of truth)
version.regex = __version__ = ["'](.*)["']
version.filename = %(source.dir)s/__init__.py

# (list) Application requirements
# seestarpy is linked into this directory as a junction (crowdsky_app/seestarpy ->
# D:\Repos\seestarpy\src\seestarpy). Run once after a fresh clone:
#   PowerShell: New-Item -ItemType Junction -Path crowdsky_app\seestarpy -Target D:\Repos\seestarpy\src\seestarpy
# Buildozer follows the junction and bundles the source. Transitive deps listed here:
requirements = python3,kivy,requests,urllib3,certifi,charset_normalizer,idna,pysmb,pyasn1,websockets,tzlocal

# (str) Supported orientation (one of landscape, sensorLandscape, portrait or all)
orientation = portrait

# (bool) Indicate if the application should be fullscreen or not
fullscreen = 0

# (string) Presplash background color (for android toolchain)
android.presplash_color = #1a1a2e

#
# Android specific
#

# (list) Permissions
android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE

# (int) Target Android API, should be as high as possible.
android.api = 33

# (int) Minimum API your APK / AAB will support.
android.minapi = 21

# (bool) If True, then automatically accept SDK license agreements.
android.accept_sdk_license = True

# (str) The Android arch to build for, choices: armeabi-v7a, arm64-v8a, x86, x86_64
android.archs = arm64-v8a

# (bool) enables Android auto backup feature (Android API >=23)
android.allow_backup = True

[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug (with command output))
log_level = 2

# (int) Display warning if buildozer is run as root (0 = False, 1 = True)
warn_on_root = 1
