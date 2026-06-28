@echo off
setlocal
chcp 65001 >nul
title NatureDrawImage

set "ROOT_DIR=%~dp0"
set "VENV_DIR=%ROOT_DIR%natureDrawImage-env"
set "VENV_CFG=%VENV_DIR%\pyvenv.cfg"
set "PYTHON_PATH_I=%ROOT_DIR%..\Py64-311\python-3.11.8.amd64\python.exe"

cd /d "%ROOT_DIR%"

echo ========================================
echo   Current dir: %cd%
echo   Venv: %VENV_DIR%
echo ========================================

:: ── 处理命令参数 ──
if /i "%1"=="stop" goto stop
if /i "%1"=="restart" goto restart

:: ── 确保虚拟环境存在 ──
if not exist "%VENV_DIR%\Scripts\python.exe" goto create_venv
goto check_deps

:create_venv
echo [1/3] Creating virtual environment...
set "PYTHON_EXE="

if exist "%PYTHON_PATH_I%" (
    set "PYTHON_EXE=%PYTHON_PATH_I%"
) else (
    if exist "%VENV_CFG%" (
        for /f "tokens=1,* delims== " %%a in ('findstr /b "home" "%VENV_CFG%"') do set "PYTHON_EXE=%%b\python.exe"
    )
)

if not defined PYTHON_EXE (
    echo [ERROR] Cannot locate Python interpreter.
    echo   Expected: %PYTHON_PATH_I%
    echo   Or install Python 3.11 and create venv manually.
    pause
    exit /b 1
)

echo   Using Python: %PYTHON_EXE%
if not exist "%PYTHON_EXE%" (
    echo [ERROR] Python not found at: %PYTHON_EXE%
    pause
    exit /b 1
)

"%PYTHON_EXE%" -m venv "%VENV_DIR%" --prompt "ndi" --clear
if errorlevel 1 (
    echo [ERROR] Failed to create virtual environment.
    pause
    exit /b 1
)

echo [2/3] Installing dependencies...
"%VENV_DIR%\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install requirements.txt.
    pause
    exit /b 1
)

"%VENV_DIR%\Scripts\python.exe" -m pip install pymysql
if errorlevel 1 (
    echo [ERROR] Failed to install pymysql.
    pause
    exit /b 1
)

echo [3/3] Done. Starting server...
goto start_loop

:check_deps
echo [OK] Virtual env found
echo [OK] Checking dependencies...
"%VENV_DIR%\Scripts\python.exe" -c "import fastapi,uvicorn,pymysql" 2>nul
if errorlevel 1 (
    echo [WARN] Dependencies missing, installing...
    "%VENV_DIR%\Scripts\python.exe" -m pip install -r requirements.txt
    "%VENV_DIR%\Scripts\python.exe" -m pip install pymysql
)

echo ========================================
echo   Local: http://127.0.0.1:8080
echo   Config loaded from .env by Python
echo   Auto-restart on crash / Ctrl+C to exit
echo ========================================

:start_loop
echo.
echo [%time%] Starting...
echo   Ctrl+C = graceful shutdown (wait for current task, then safe exit)
"%VENV_DIR%\Scripts\python.exe" -m uvicorn web.app:app --host 127.0.0.1 --port 8080 --forwarded-allow-ips 127.0.0.1 --timeout-graceful-shutdown 60

echo [%time%] Exited, restarting in 3s...
timeout /t 3 /nobreak >nul
goto start_loop

:stop
echo [1/2] Stopping Web server gracefully...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8080 ^| findstr LISTENING') do (
    set "PID=%%a"
    goto :found
)
echo   No Web server running on port 8080.
pause
exit /b

:found
echo   Found PID %PID%, sending shutdown signal...
taskkill /pid %PID% >nul 2>&1
if %errorlevel% equ 0 (
    echo   Waiting up to 10 seconds for graceful exit...
    set /a count=0
    :wait_loop
    timeout /t 1 /nobreak >nul
    set /a count+=1
    tasklist /fi "pid eq %PID%" | find /i "%PID%" >nul 2>&1
    if %errorlevel% neq 0 goto :exited
    if %count% lss 10 goto wait_loop
    echo   [WARN] Process not responding, force killing...
    taskkill /f /pid %PID% >nul 2>&1
) else (
    echo   [WARN] Graceful shutdown failed, force killing...
    taskkill /f /pid %PID% >nul 2>&1
)
:exited
echo [2/2] Web server stopped.
pause
exit /b

:restart
echo Restarting Web server...
call :stop
timeout /t 2 /nobreak >nul
goto start_loop