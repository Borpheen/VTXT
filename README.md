# VTXT

VTXT is a lightweight dual countdown timer for Windows with an always-on-top overlay, custom alarms, configurable hotkeys, and saved settings.

## Download

For normal users, download the installer from the **Releases** section:

```text
VTXT_Setup_v3.0.0.exe
```

No Python installation is required.

## Features

- Dual independent countdown timers
- Always-on-top overlay pill
- Overlay visibility, lock, size, and opacity controls
- Built-in alarm sounds
- Custom audio file support
- Configurable keyboard and mouse-button hotkeys
- Settings saved under `%LOCALAPPDATA%\VTXT`

## Notes

VTXT does not inject input, remap controls, modify game files, read game memory, or interact with Battlefield 6 directly. It is a normal Windows desktop timer and overlay application.

## For Developers

To run or build from source, install the dependencies:

```powershell
py -m pip install -r requirements.txt
```

Build the executable:

```powershell
py -m PyInstaller --onefile --windowed `
  --name VTXT `
  --icon ".\vtxt.ico" `
  --add-data ".\vtxt_banner.png;." `
  --add-data ".\vtxt.ico;." `
  ".\VTXT_final_cleanup.py"
```

Build the installer with Inno Setup:

```powershell
& "E:\Inno Setup 6\ISCC.exe" ".\VTXT_Installer.iss"
```

## Installer

The installer is built with Inno Setup and installs VTXT as a per-user Windows application.

Default installed location:

```text
%LOCALAPPDATA%\Programs\VTXT
```

Saved settings location:

```text
%LOCALAPPDATA%\VTXT\settings.json
```

## Publisher

VTX-LordBust
