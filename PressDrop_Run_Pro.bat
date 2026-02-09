@echo off
setlocal
cd /d %~dp0

REM --- CONFIGURATION ---
set VENV_DIR=venv
set LOG=run_log.txt
REM ---------------------

echo =============================== > "%LOG%"
echo PressDrop Pro Launcher >> "%LOG%"
echo =============================== >> "%LOG%"

REM 1. Check if Python is installed
python --version >> "%LOG%" 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found! 
    echo Please install Python 3.10+ from python.org and check "Add to PATH" during installation.
    pause
    exit /b 1
)

REM 2. Check if Virtual Environment exists
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo [First Run] Setting up PressDrop environment...
    echo This only happens once. Please wait.
    
    REM Create Venv
    python -m venv %VENV_DIR%
    
    REM Activate and Install
    call "%VENV_DIR%\Scripts\activate.bat"
    
    echo [First Run] Installing dependencies...
    python -m pip install --upgrade pip >> "%LOG%" 2>&1
    
    if exist requirements.txt (
        pip install -r requirements.txt >> "%LOG%" 2>&1
    ) else (
        echo [Warning] requirements.txt not found. Installing defaults.
        pip install pypdf Pillow >> "%LOG%" 2>&1
    )
    
    echo [Success] Setup complete.
)

REM 3. Launch the App
echo [Launching] PressDrop...
call "%VENV_DIR%\Scripts\activate.bat"
python src\pressdrop_gui.py >> "%LOG%" 2>&1

if errorlevel 1 (
    echo.
    echo [CRASH] The app closed unexpectedly.
    echo Check %LOG% for error details.
    pause
)