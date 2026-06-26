@echo off
title Sync Tool
set "ROOT_DIR=%~dp0"
set "VENV_DIR=%ROOT_DIR%natureDrawImage-env"
cd /d "%ROOT_DIR%"

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo ERROR: Virtual environment not found:
    echo   %VENV_DIR%
    echo Please create/install it first, or run start-Py64-311.bat.
    pause
    exit /b 1
)

"%VENV_DIR%\Scripts\python.exe" scripts\sync_gui.py
if %errorlevel% neq 0 (
    pause
)
