@echo off
rem ===========================================================================
rem  CryNet - copy the sketches into the Arduino sketchbook
rem
rem  The Arduino IDE can only build a sketch that sits in its own sketchbook
rem  (C:\Users\HP\Documents\Arduino).  The real source lives in the
rem  repository, so this copies it across.  Run it after you change a
rem  sketch, then press Upload in the Arduino IDE.
rem ===========================================================================
setlocal
title CryNet - copy sketches to the Arduino sketchbook

cd /d "%~dp0..\.."

set "BOOK=%USERPROFILE%\Documents\Arduino"
if not exist "%BOOK%" (
    echo.
    echo ERROR: the Arduino sketchbook is not there:
    echo   %BOOK%
    echo   Open the Arduino IDE once, so it creates it, and run this again.
    echo.
    pause
    exit /b 1
)

echo.
echo   Copying the sketches into %BOOK%
echo.
if exist "%BOOK%\node_crynet" rmdir /s /q "%BOOK%\node_crynet"
if exist "%BOOK%\node_capture" rmdir /s /q "%BOOK%\node_capture"
if exist "%BOOK%\wearable_crynet" rmdir /s /q "%BOOK%\wearable_crynet"

xcopy /e /i /y /q "firmware\node\node_crynet"    "%BOOK%\node_crynet"    >nul
xcopy /e /i /y /q "firmware\node\node_capture"  "%BOOK%\node_capture"  >nul
xcopy /e /i /y /q "firmware\wearable\wearable_crynet" "%BOOK%\wearable_crynet" >nul

if not exist "%BOOK%\node_crynet\node_crynet.ino" (
    echo   The copy failed.  Nothing was changed in the sketchbook.
    echo.
    pause
    exit /b 1
)
if not exist "%BOOK%\wearable_crynet\wearable_crynet.ino" (
    echo   The copy failed.  Nothing was changed in the sketchbook.
    echo.
    pause
    exit /b 1
)

echo   done.
echo.
echo   Now in the Arduino IDE:
echo     File menu, then Open...  then pick
echo       %BOOK%\node_crynet\node_crynet.ino
echo     or
echo       %BOOK%\wearable_crynet\wearable_crynet.ino
echo.
pause
