@echo off
setlocal
cd /d "%~dp0"
title Event Photos setup

echo Setting up Event Photos. This needs internet and can take several minutes.
echo.

rem The libraries only ship ready-made packages for Python 3.10 to 3.14. Newer
rem versions make pip try to compile them, which fails without build tools.
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if (3,10) <= sys.version_info[:2] <= (3,14) else 1)" >nul 2>&1
    if errorlevel 1 (
        echo The existing environment uses an unsupported Python version. Recreating it...
        rmdir /s /q ".venv"
    )
)

if not exist ".venv\Scripts\python.exe" (
    where py >nul 2>&1
    if errorlevel 1 (
        echo Python was not found. Install Python 3.12 from https://www.python.org/downloads/release/python-3129/
        echo and tick "Add python.exe to PATH", then run this file again.
        echo.
        pause
        exit /b 1
    )
    set "PYVER="
    for %%V in (3.12 3.13 3.11 3.10 3.14) do (
        if not defined PYVER (
            py -%%V -c "import sys" >nul 2>&1
            if not errorlevel 1 set "PYVER=%%V"
        )
    )
    if not defined PYVER (
        echo No supported Python was found. This app needs Python 3.10 to 3.14.
        echo Newer versions such as 3.15 do not work yet. Install Python 3.12 from
        echo https://www.python.org/downloads/release/python-3129/ and run this file again.
        echo.
        pause
        exit /b 1
    )
    echo Creating the Python environment with Python %PYVER%...
    py -%PYVER% -m venv .venv
    if errorlevel 1 goto :failed
)

".venv\Scripts\python.exe" -m pip install --upgrade pip

rem Look for an NVIDIA graphics card so the default choice fits this PC.
set "DEFAULT=1"
set "GPUNAME="
where nvidia-smi >nul 2>&1
if not errorlevel 1 (
    for /f "usebackq delims=" %%G in (`nvidia-smi --query-gpu=name --format=csv,noheader 2^>nul`) do (
        if not defined GPUNAME set "GPUNAME=%%G"
    )
)
if defined GPUNAME set "DEFAULT=2"

echo Which PyTorch build should be installed?
echo   1  CPU only        works on every PC, smaller download, slower
echo   2  NVIDIA GPU      CUDA 12.6, for GTX 10 series up to RTX 40 series
echo   3  NVIDIA GPU      CUDA 12.8, for RTX 50 series
echo.
if defined GPUNAME echo Detected: %GPUNAME%
if not defined GPUNAME echo No NVIDIA graphics card was detected, so the CPU build is recommended.
echo Press a number, or wait 20 seconds for the recommended choice ^(%DEFAULT%^).
choice /c 123 /n /t 20 /d %DEFAULT% /m "Your choice: "
set "PICK=%errorlevel%"
echo.

set "TORCH_INDEX=cpu"
if "%PICK%"=="2" set "TORCH_INDEX=cu126"
if "%PICK%"=="3" set "TORCH_INDEX=cu128"

echo Installing PyTorch ^(%TORCH_INDEX% build^)...
".venv\Scripts\python.exe" -m pip install --force-reinstall torch torchvision --index-url https://download.pytorch.org/whl/%TORCH_INDEX%
if errorlevel 1 goto :failed

if not "%TORCH_INDEX%"=="cpu" (
    ".venv\Scripts\python.exe" -c "import torch,sys; sys.exit(0 if torch.cuda.is_available() else 1)" >nul 2>&1
    if errorlevel 1 (
        echo.
        echo Note: the GPU build is installed, but no usable NVIDIA GPU was found.
        echo Update your NVIDIA driver, or run Setup.bat again and choose 1 for CPU.
    ) else (
        echo GPU check passed. Choose it in Settings inside the app.
    )
)

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
