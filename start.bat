@echo off
chcp 65001 >nul
title Natural Language Image Generation

cd /d "%~dp0"

echo ========================================
echo   Current dir: %cd%
echo ========================================

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual env not found: .venv\Scripts\python.exe
    pause
    exit /b 1
)

echo [OK] Virtual env found

echo [OK] Checking dependencies...
.venv\Scripts\python.exe -c "import fastapi, uvicorn" 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Dependencies missing, run: pip install -r web/requirements.txt
    pause
    exit /b 1
)

echo ========================================
echo   Local: http://127.0.0.1:8080
echo   Config loaded from .env by Python
echo   Auto-restart on crash / Ctrl+C to exit
echo ========================================

:loop
echo.
echo [%time%] Starting...
echo   Ctrl+C = graceful shutdown (wait for current task, then safe exit)
.venv\Scripts\python.exe -m uvicorn web.app:app --host 127.0.0.1 --port 8080 --forwarded-allow-ips 127.0.0.1 --timeout-graceful-shutdown 60

echo [%time%] Exited cleanly, restarting in 3s...
timeout /t 3 /nobreak >nul
goto loop
