# Plans for the new version (v3) of the crowdsky app
I'm aiming to recreate most of the crowdsky web UI (see D:\Repos\CrowdSky\web) in the app, with the "upload.php" functionality being replaced by the choose-frames-from-seestar/harddrive screens, and also incorporating the functionality from the server-worker for the PC-version for locally stacking raw frames    

## What to keep from the existing version2 of the app (crowdsky_app_2/)
- The splash screen and login credential manager
- The choose-frames (from a networked seestar) page
- The stacking and upload jobs page and jobs manager

## What to add
- A new home screen that gives the user the 4 options:
  - Sky Map
  - Gallery
  - Donate From Seestar
  - Donate From Harddrive (deactivated if on an Android platform)
- A sky-map page (D:\Repos\CrowdSky\crowdsky_app\screens_layouts\2-sky-map.png) : mirrors the functionality of the sky-map in the web/ ui on stacks.php 
- A gallery page (D:\Repos\CrowdSky\crowdsky_app\screens_layouts\3-gallery.png) : similar to the "table view" in the web/ ui on stacks.php, except instead of table rows, it shows the thumbnails of the filtered selection, 9 (or 16) per page
- A choose-frames-from-hard-drive page (D:\Repos\CrowdSky\crowdsky_app\screens_layouts\5-choose-frames-from_harddrive.png) : this page mirrors the existing functionality of the choose-frames-from-seestar page, but instead of searching the network for "seestar-N.local" mDNS names, it lets the user choose a file path on their PC, then from this top directory crawls all sub-directories for suitable files to stack. When stacking, the app should essentially re-use the code from our server-worker system (D:\Repos\CrowdSky\worker), but utilise the users PC to do the work (i.e. do NOT upload 10+ GB via our web interface).
