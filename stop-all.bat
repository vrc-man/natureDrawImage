@echo off
chcp 65001 >nul
title Stop NatureDrawImage

cd /d "%~dp0"

if not exist "natureDrawImage-env\Scripts\python.exe" (
    echo [ERROR] Virtual env not found
    pause
    exit /b 1
)

echo ========================================
echo  Stop NatureDrawImage Web
echo  MySQL stays running (开机自启)
echo ========================================
echo.

natureDrawImage-env\Scripts\python.exe stop.py

echo.
pause
