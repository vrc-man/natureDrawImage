@echo off
chcp 65001 >nul
title NatureDrawImage Web

cd /d "%~dp0"

if not exist "natureDrawImage-env\Scripts\python.exe" (
    echo [ERROR] Virtual env not found: natureDrawImage-env\Scripts\python.exe
    pause
    exit /b 1
)

if not exist ".env" (
    echo [ERROR] .env not found
    pause
    exit /b 1
)

echo ========================================
echo   Current dir: %cd%
echo   .env loaded by Python
echo   MySQL auto-managed by start.py
echo ========================================

:loop
echo.
echo [%time%] Starting...
echo   Ctrl+C = graceful Web stop, then choose restart or exit
natureDrawImage-env\Scripts\python.exe start.py

echo.
choice /c NY /n /m "N=restart, Y=close Web (MySQL stays running): "
if errorlevel 2 goto exit
if errorlevel 1 goto loop

:exit
echo.
echo Web closed. MySQL is still running.
echo To stop MySQL safely, run:  natureDrawImage-env\Scripts\python.exe stop.py
pause
exit /b 0
