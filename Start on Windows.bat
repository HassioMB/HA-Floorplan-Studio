@echo off
title HA Floorplan Studio v1.0.0
cd /d "%~dp0"

cls
echo ========================================
echo         HA Floorplan Studio v1.0.0
echo ========================================
echo.

where py >nul 2>&1

if %errorlevel%==0 (
    set "PYTHON=py -3"
    goto :python_found
)

where python >nul 2>&1

if %errorlevel%==0 (
    set "PYTHON=python"
    goto :python_found
)

echo ERROR: Python 3 is not installed.
echo.
echo Install Python 3 from:
echo https://www.python.org/downloads/
echo.
echo IMPORTANT:
echo Enable "Add Python to PATH" during installation.
echo.
pause
exit /b 1


:python_found

if not exist ".venv" (
    echo First start - creating local environment...
    %PYTHON% -m venv .venv

    if errorlevel 1 (
        echo.
        echo ERROR: Could not create Python environment.
        pause
        exit /b 1
    )
)

call ".venv\Scripts\activate.bat"

echo Checking dependencies...
python -m pip install --quiet -r requirements.txt

if errorlevel 1 (
    echo.
    echo ERROR: Could not install required Python packages.
    pause
    exit /b 1
)

echo.
echo Starting HA Floorplan Studio...
echo Address: http://127.0.0.1:8088/
echo.
echo Keep this window open while using the editor.
echo Press Ctrl+C to stop.
echo.

start "" "http://127.0.0.1:8088/"

set PORT=8088
python server.py

echo.
echo HA Floorplan Studio stopped.
pause
