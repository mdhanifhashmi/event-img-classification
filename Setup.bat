@echo off
setlocal
cd /d "%~dp0"
title Event Photos setup

echo Setting up Event Photos. This needs internet and can take several minutes.
echo.

if not exist ".venv\Scripts\python.exe" (
    where py >nul 2>&1
    if errorlevel 1 (
        echo Python was not found. Install it from https://www.python.org/downloads/
        echo and tick "Add python.exe to PATH", then run this file again.
        echo.
        pause
        exit /b 1
    )
    echo Creating the Python environment...
    py -3 -m venv .venv
    if errorlevel 1 goto :failed
)

echo Installing PyTorch ^(CPU build^)...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
if errorlevel 1 goto :failed

echo Installing the other libraries...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :failed

echo.
echo Setup finished. Open "Event Photos.bat" to start the app.
echo.
pause
exit /b 0

:failed
echo.
echo Setup stopped because of an error. Read the lines above, fix the problem, and run Setup.bat again.
echo.
pause
exit /b 1
