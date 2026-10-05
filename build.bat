@echo off
setlocal
cd /d "%~dp0"

py -m pip install -r requirements.txt
py -m pip install pyinstaller

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

pyinstaller --noconfirm --clean WhereDidMyTerminalGo.spec

echo.
echo Build complete:
echo dist\WhereDidMyTerminalGo.exe
pause
