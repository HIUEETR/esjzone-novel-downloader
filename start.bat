@echo off
setlocal EnableDelayedExpansion

REM Check if python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    pause
    exit /b 1
)

REM Check if uv is installed
uv --version >nul 2>&1
if errorlevel 1 (
    echo [WARN] uv is not installed. Attempting to install uv via pip...
    
    python -m pip install uv
    if errorlevel 1 (
        echo [ERROR] Failed to install uv.
        pause
        exit /b 1
    )
)

REM Run with uv (it automatically handles venv and dependencies from pyproject.toml)
echo [INFO] Starting application with uv...
uv run main.py

if errorlevel 1 (
    echo [ERROR] Application exited with error.
    pause
)
