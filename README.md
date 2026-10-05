# WhereDidMyTerminalGo

A small Windows tray application for launching and stopping development commands silently in the background.

## Features

- Modern dark Tkinter UI
- Select a project directory
- Configure multiple commands
- Start and stop all commands
- Commands run without visible console windows
- Closing the window hides the app to the Windows system tray
- Tray menu: Open, Start, Stop, Exit
- Per-command logs are stored in `%LOCALAPPDATA%\WhereDidMyTerminalGo\logs`
- Child processes are terminated with `taskkill /T /F`
- Packaged as a single Windows executable

## Default Commands

```text
uv run src/main.py
cloudflared tunnel run
```

`uv` and `cloudflared` must be installed and available on `PATH` on the Windows machine where the application is used.

## Run from Source

```powershell
py -m pip install -r requirements.txt
py app.py
```

## Build the EXE

Make sure these files are present in the project root:

```text
app.py
requirements.txt
WhereDidMyTerminalGo.spec
icon.ico
icon.png
```

### Using the build script

```powershell
.\build.bat
```

### Or manually

```powershell
py -m pip install -r requirements.txt
py -m pip install pyinstaller
pyinstaller --noconfirm --clean WhereDidMyTerminalGo.spec
```

The executable will be created at:

```text
dist\WhereDidMyTerminalGo.exe
```

## Repository Structure

```text
WhereDidMyTerminalGo/
├── app.py
├── requirements.txt
├── WhereDidMyTerminalGo.spec
├── build.bat
├── icon.ico
├── icon.png
├── .gitignore
├── README.md
└── .github/
    └── workflows/
        └── build.yml
```

## Distribution

The source code is available in this repository.

The compiled `WhereDidMyTerminalGo.exe` is distributed through **GitHub Releases** rather than being committed to the repository.

## Runtime Logs

Logs are intentionally stored outside the PyInstaller one-file temporary extraction directory.

```text
%LOCALAPPDATA%\WhereDidMyTerminalGo\logs
```

Log filenames are generated from the configured command names.

## Requirements

- Windows 10/11
- Python 3.10+ for running from source
- `uv` and `cloudflared` if using the default commands

Python dependencies:

```text
pystray
Pillow
```

## GitHub Actions

The repository includes a GitHub Actions workflow that builds the Windows executable.

The workflow can be triggered manually or by pushing a version tag such as:

```text
v2026.1
```

The resulting executable is uploaded as a GitHub Actions artifact.

## License

This project is licensed under the MIT License.

See the [LICENSE](LICENSE) file for the full license text.

## Author

Made by **BiLLuMiNaTi**.