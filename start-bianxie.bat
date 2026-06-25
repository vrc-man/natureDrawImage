@echo off
chcp 65001 >nul
title Natural Language Image Generation

cd /d "%~dp0"

echo ========================================
echo   Current dir: %cd%
echo ========================================

set "VENV_DIR=natureDrawImage-env"

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo ERROR: Virtual environment not found
    pause
    exit /b 1
)

echo OK: Virtual environment found

echo OK: Checking dependencies...
"%VENV_DIR%\Scripts\python.exe" -c "import fastapi,uvicorn"
if %errorlevel% neq 0 (
    echo ERROR: Dependencies missing
    pause
    exit /b 1
)

echo ========================================
echo   Local: http://127.0.0.1:8080
echo ========================================

:loop
echo.
echo Starting server...
"%VENV_DIR%\Scripts\python.exe" -m uvicorn web.app:app --host 127.0.0.1 --port 8080 --forwarded-allow-ips=127.0.0.1 --timeout-graceful-shutdown 60

echo Server exited cleanly, restarting in 3s...
timeout /t 3 /nobreak >nul
goto loop