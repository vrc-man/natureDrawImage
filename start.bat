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
echo   Loading config from .env file...
echo ========================================

REM 从 .env 文件加载环境变量
if exist ".env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%a in (".env") do (
        set "%%a=%%b"
    )
    echo [OK] .env loaded
) else (
    echo [WARNING] .env file not found, using system environment variables
    echo [WARNING] Copy .env.example to .env and fill in your config
)

echo ========================================
echo   Local: http://%WEB_HOST%:%WEB_PORT%
echo   Auto-restart on crash / Ctrl+C to exit
echo ========================================

:loop
echo.
echo [%time%] Starting...

REM 如果 .env 未配置，使用回退默认值
if "%WEB_HOST%"=="" set "WEB_HOST=127.0.0.1"
if "%WEB_PORT%"=="" set "WEB_PORT=8080"

.venv\Scripts\python.exe -m uvicorn web.app:app --host %WEB_HOST% --port %WEB_PORT% --forwarded-allow-ips 127.0.0.1

echo [%time%] Stopped, restarting in 3s...
timeout /t 3 /nobreak >nul
goto loop
