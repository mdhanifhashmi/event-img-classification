@echo off
setlocal
cd /d "%~dp0"
title Event Photos

if not exist ".venv\Scripts\python.exe" (
    echo The Python environment has not been set up yet.
    echo Double-click "Setup.bat" once, then open this file again.
    echo.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -c "import customtkinter, PIL, yaml" >nul 2>&1
if errorlevel 1 (
    echo Some libraries are missing from the environment.
    echo Double-click "Setup.bat" to install them, then open this file again.
    echo.
    pause
    exit /b 1
)

rem pythonw opens the window without a black console behind it.
start "" ".venv\Scripts\pythonw.exe" -m src.gui
exit /b 0
