@echo off
rem ===========================================================================
rem  CryNet - flash a unit (hub, cot node or wearable)
rem
rem  Double-click this file.  Press the key for the unit, type the port,
rem  and it is done.
rem
rem  It needs no Arduino IDE, no PlatformIO, no network - only esptool,
rem  which it looks for next to this file, then in PlatformIO's folder,
rem  then on the PATH.
rem
rem  The images it writes are the .bin files in the hub, node and wearable
rem  folders next to this script.
rem ===========================================================================
setlocal enabledelayedexpansion
title CryNet - flash a unit
cd /d "%~dp0"

rem --- 1. the images must be here ------------------------------------------
if not exist "hub\firmware.bin" (
    echo.
    echo ERROR: the firmware images are not next to this file.
    echo   Expected: hub\firmware.bin  -- in the folder this script is in.
    echo   Copy the whole folder - hub, node, wearable - with this script.
    echo.
    pause
    exit /b 1
)

rem --- 2. find esptool ------------------------------------------------------
set "ESP="
if exist "esptool.exe" set "ESP=esptool.exe"
if not defined ESP if exist "%USERPROFILE%\.platformio\packages\tool-esptool\esptool.exe" set "ESP=%USERPROFILE%\.platformio\packages\tool-esptool\esptool.exe"
if not defined ESP for /f "delims=" %%e in ('where esptool.exe 2^>nul') do if not defined ESP set "ESP=%%e"
if not defined ESP for /f "delims=" %%e in ('where esptool 2^>nul') do if not defined ESP set "ESP=%%e"

if not defined ESP (
    echo.
    echo ERROR: esptool was not found on this PC.
    echo.
    echo   Looked next to this file, in
    echo   %USERPROFILE%\.platformio\packages\tool-esptool\esptool.exe
    echo   and for "esptool" on the PATH.
    echo.
    echo   Fix it by copying esptool.exe into this folder, or by running
    echo     pip install esptool
    echo   and then running this script again.
    echo.
    pause
    exit /b 1
)

echo.
echo   esptool: %ESP%
echo.

rem --- 3. check the images are intact and up to date -----------------------
rem  check_prebuilt.ps1 does two things: it verifies every image against
rem  SHA256SUMS (so a damaged or truncated file cannot be written), and it
rem  compares the source in the tree against the record of what the images
rem  were built from (so a stale image cannot be written either).
powershell -NoProfile -ExecutionPolicy Bypass -File "check_prebuilt.ps1"
if errorlevel 1 (
    echo.
    echo   Nothing was flashed.
    echo.
    pause
    exit /b 1
)
echo.

:MENU
cls
echo ======================================================================
echo   Which unit are you flashing?
echo.
echo     1 = hub        the ESP32-S3 board with the screen
echo     2 = cot node   the ESP32-C3 board with the microphone
echo     3 = wearable   the ESP32-C3 board with the wrist screen
echo     4 = just tell me which board is on which port - flashes nothing
echo.
set "CHOICE="
set /p CHOICE=   Type 1, 2, 3 or 4 and press Enter:
for /f "tokens=1 delims= " %%c in ("!CHOICE!") do set "CHOICE=%%c"
echo.
if "!CHOICE!"=="1" goto HUB
if "!CHOICE!"=="2" goto NODE
if "!CHOICE!"=="3" goto WEARABLE
if "!CHOICE!"=="4" goto IDENTIFY
echo   That is not one of the choices.  Try again.
goto MENU

rem ---------------------------------------------------------------------------
:IDENTIFY
cls
echo   The ports on this PC right now:
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "list_ports_verbose.ps1"
echo.
echo   Now reading the MAC address of every board on those ports.
echo   A board that has never been flashed still has a MAC.
echo.
for /f "delims=" %%p in ('powershell -NoProfile -ExecutionPolicy Bypass -File "list_ports.ps1"') do call :MAC "%%p"
echo.
echo   Write the MAC down next to the board.  The COM number can change
echo   when you move the cable, but the MAC never changes.
echo.
pause
exit /b 0

:MAC
set "PORT=%~1"
echo     %PORT% ...
rem  match the MAC address itself (six hex pairs) rather than a label,
rem  so it works whatever esptool calls the line
set "RE=[0-9A-Fa-f][0-9A-Fa-f]:[0-9A-Fa-f][0-9A-Fa-f]:[0-9A-Fa-f][0-9A-Fa-f]:[0-9A-Fa-f][0-9A-Fa-f]:[0-9A-Fa-f][0-9A-Fa-f]:[0-9A-Fa-f][0-9A-Fa-f]"
"%ESP%" --chip esp32c3 --port %PORT% chip-id 2>nul | findstr /R /C:"%RE%" >nul
if not errorlevel 1 (
    echo       this is an ESP32-C3 - a cot node or the wearable
    "%ESP%" --chip esp32c3 --port %PORT% chip-id 2>nul | findstr /R /C:"%RE%"
    goto :eof
)
"%ESP%" --chip esp32s3 --port %PORT% chip-id 2>nul | findstr /R /C:"%RE%" >nul
if not errorlevel 1 (
    echo       this is an ESP32-S3 - the hub
    "%ESP%" --chip esp32s3 --port %PORT% chip-id 2>nul | findstr /R /C:"%RE%"
    goto :eof
)
echo       nothing answered on this port
goto :eof

rem ---------------------------------------------------------------------------
:HUB
set "ROLE=hub"
set "CHIP=esp32s3"
set "DIR=hub"
set "OFF1=0x0"
set "F1=bootloader.bin"
set "OFF2=0x8000"
set "F2=partitions.bin"
set "OFF3=0x10000"
set "F3=firmware.bin"
set "OFF4="
set "F4="
set "SIZE=0x1000000"
goto ASKPORT

:NODE
set "ROLE=node"
set "CHIP=esp32c3"
set "DIR=node"
set "OFF1=0x0"
set "F1=bootloader.bin"
set "OFF2=0x8000"
set "F2=partitions.bin"
set "OFF3=0xe000"
set "F3=boot_app0.bin"
set "OFF4=0x10000"
set "F4=app.bin"
set "SIZE=0x400000"
goto ASKPORT

:WEARABLE
set "ROLE=wearable"
set "CHIP=esp32c3"
set "DIR=wearable"
set "OFF1=0x0"
set "F1=bootloader.bin"
set "OFF2=0x8000"
set "F2=partitions.bin"
set "OFF3=0xe000"
set "F3=boot_app0.bin"
set "OFF4=0x10000"
set "F4=app.bin"
set "SIZE=0x400000"
goto ASKPORT

:ASKPORT
cls
echo   You are flashing the %ROLE%.
echo.
echo   The ports on this PC right now:
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "list_ports_verbose.ps1"
echo.
set "PORT="
set /p PORT=Which port is the %ROLE% on - for example COM31 -
for /f "tokens=1 delims= " %%p in ("!PORT!") do set "PORT=%%p"
if "!PORT!"=="" (
    echo.
    echo   You have to say which port.  Nothing was flashed.
    pause
    exit /b 1
)
echo.

rem  refuse a port that is not plugged in right now - this is the mistake
rem  recorded as I-40, and it is the one that costs the most time
set "SEEN="
for /f "delims=" %%p in ('powershell -NoProfile -ExecutionPolicy Bypass -File "list_ports.ps1"') do (
    if /i "%%p"=="%PORT%" set "SEEN=1"
)
if not defined SEEN (
    echo   There is no port called %PORT% on this PC right now.
    echo   Look at the list above and type one of those exactly.
    echo   Nothing was flashed.
    echo.
    pause
    exit /b 1
)

rem --- backup ---------------------------------------------------------------
set "BAK=%USERPROFILE%\CryNet_Backups"
if not exist "%BAK%" mkdir "%BAK%" >nul 2>&1
set "BAKFILE=%BAK%\%ROLE%_%PORT%_backup.bin"
echo   Backing up what is on the board right now to
echo     %BAKFILE%
echo   This takes a minute and is your way back if anything goes wrong.
echo.
"%ESP%" --chip %CHIP% --port %PORT% --baud 921600 read-flash 0x0 %SIZE% "%BAKFILE%"
if errorlevel 1 (
    echo.
    echo   The backup failed.
    echo.
    echo   That is normal for a brand-new board, and it also happens when
    echo   the board is in its bootloader - hold the BOOT button while
    echo   plugging it in and it shows up as a download port.
    echo.
    set "ANS="
    set /p ANS=   Flash anyway without a backup?  Type y to go ahead:
    if /i "!ANS!"=="y" goto FLASHNOW
    echo   Nothing was flashed.
    echo.
    pause
    exit /b 1
)
echo.

:FLASHNOW

rem --- flash ----------------------------------------------------------------
echo   Flashing the %ROLE% on %PORT% ...
echo.
if "%ROLE%"=="hub" (
    "%ESP%" --chip %CHIP% --port %PORT% --baud 921600 write-flash %OFF1% "%DIR%\%F1%" %OFF2% "%DIR%\%F2%" %OFF3% "%DIR%\%F3%"
) else (
    "%ESP%" --chip %CHIP% --port %PORT% --baud 921600 write-flash %OFF1% "%DIR%\%F1%" %OFF2% "%DIR%\%F2%" %OFF3% "%DIR%\%F3%" %OFF4% "%DIR%\%F4%"
)
if errorlevel 1 (
    echo.
    echo   THE FLASH FAILED.  Nothing was written, or only partly.
    echo   See GETTING_STARTED_FLASHING.md, the section "When it fails".
    echo.
    pause
    exit /b 1
)

echo.
echo   Starting the board ...
"%ESP%" --chip %CHIP% --port %PORT% run >nul 2>&1
echo.
echo ======================================================================
echo   DONE.  The %ROLE% on %PORT% now has the CryNet firmware.
echo.
echo   To see what it says, open a serial monitor on %PORT% at 115200
echo   baud and press the board's RESET button.
echo   The full check list is in GETTING_STARTED_FLASHING.md.
echo ======================================================================
echo.
pause
exit /b 0
