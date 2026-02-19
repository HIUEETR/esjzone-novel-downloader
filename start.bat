@echo off
setlocal EnableDelayedExpansion

REM Check if requirements.txt exists
if exist requirements.txt (
    echo [INFO] requirements.txt found. Using pip...
    
    REM Check if python is installed
    python --version >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Python is not installed or not in PATH.
        pause
        exit /b 1
    )

    REM Create virtual environment if it doesn't exist
    if not exist venv (
        echo [INFO] Creating virtual environment...
        python -m venv venv
    )

    REM Activate virtual environment
    call venv\Scripts\activate

    REM Install dependencies
    echo [INFO] Installing dependencies from requirements.txt...
    pip install -r requirements.txt

    REM Run the application
    echo [INFO] Starting application...
    python main.py
    
    REM Deactivate
    deactivate
) else (
    echo [INFO] requirements.txt not found. Using uv...

    REM Check if uv is installed
    uv --version >nul 2>&1
    if errorlevel 1 (
        echo [WARN] uv is not installed. Attempting to install uv via pip...
        
        REM Check if python is installed
        python --version >nul 2>&1
        if errorlevel 1 (
            echo [ERROR] Python is not installed. Cannot install uv.
            echo [INFO] Please install Python or uv manually.
            pause
            exit /b 1
        )
        
        pip install uv
        if errorlevel 1 (
            echo [ERROR] Failed to install uv.
            pause
            exit /b 1
        )
    )

    REM Run with uv (it automatically handles venv and dependencies from pyproject.toml)
    echo [INFO] Starting application with uv...
    uv run main.py
)

if errorlevel 1 (
    echo [ERROR] Application exited with error.
    pause
)
