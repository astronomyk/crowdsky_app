# Compiling notes for humans

## First-time setup (after fresh clone)

`crowdsky_app/seestarpy` must be a directory junction to the seestarpy repo.
Create it once with PowerShell (no admin rights needed):

```powershell
New-Item -ItemType Junction -Path crowdsky_app\seestarpy -Target D:\Repos\seestarpy\src\seestarpy
```

This makes both desktop and Buildozer/Android builds always use the live
seestarpy source. Never copy files in manually — the junction keeps it in sync.

## Run the App locally for testing

```
uv run python -m crowdsky_app
```

## Build the App

Make the app in EXE format:

```
uv run pyinstaller CrowdSky.spec --noconfirm
```

The product is found in the `dist/` folder.

Make the app in APK format over in WSL:

```
buildozer android debug
```

The product is found in the `bin/` folder.

