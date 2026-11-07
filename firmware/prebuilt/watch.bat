@echo off
rem ===========================================================================
rem  CryNet - watch what a board says
rem
rem  This is the Serial Monitor of the Arduino IDE, without the Arduino IDE.
rem  Double-click it, type the port, and the board's messages appear.
rem  Close the window (or press Ctrl+C) to stop.
rem ===========================================================================
setlocal enabledelayedexpansion
title CryNet - serial monitor
cd /d "%~dp0"

set "PORT="
set /p PORT=Which port do you want to watch - for example COM31 -
for /f "tokens=1 delims= " %%p in ("!PORT!") do set "PORT=%%p"
if "!PORT!"=="" (
    echo.
    echo   You have to say which port.
    pause
    exit /b 1
)

python "%~dp0..\..\firmware\tools\serial_monitor.py" --port !PORT!
echo.
pause
