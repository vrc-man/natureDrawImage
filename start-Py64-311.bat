@echo off
setlocal
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

:ensure_venv
if not exist "%VENV_DIR%\Scripts\python.exe" goto create_venv
goto check_python

:create_venv
echo Creating virtual environment...
set "PYTHON_EXE="

if exist "%PYTHON_PATH_I%" (
    set "PYTHON_EXE=%PYTHON_PATH_I%"
) else (
    if exist "%VENV_CFG%" (
        for /f "tokens=1,* delims== " %%a in ('findstr /b "home" "%VENV_CFG%"') do set "PYTHON_EXE=%%b\python.exe"
    )
)

if not defined PYTHON_EXE (
    echo ERROR: Cannot locate Python interpreter.
    echo Expected portable Python:
    echo   %PYTHON_PATH_I%
    echo Or install Python 3.11 and create the venv manually.
    pause
    exit /b 1
)

echo Using Python: %PYTHON_EXE%
if not exist "%PYTHON_EXE%" (
    echo ERROR: Python not found at:
    echo   %PYTHON_EXE%
    pause
    exit /b 1
)

"%PYTHON_EXE%" -m venv "%VENV_DIR%" --prompt "ndi" --clear
if errorlevel 1 (
    echo ERROR: Failed to create virtual environment.
    pause
    exit /b 1
)

"%VENV_DIR%\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install requirements.txt.
    pause
    exit /b 1
)

"%VENV_DIR%\Scripts\python.exe" -m pip install pymysql
if errorlevel 1 (
    echo ERROR: Failed to install pymysql.
    pause
    exit /b 1
)

echo Dependencies installed.

:check_python
echo OK: Checking Python...
"%VENV_DIR%\Scripts\python.exe" --version >nul 2>&1
if errorlevel 1 (
    echo WARNING: Python in venv not found, recreating...
    goto create_venv
)

echo OK: Checking dependencies...
"%VENV_DIR%\Scripts\python.exe" -c "import fastapi,uvicorn,pymysql"
if errorlevel 1 (
    echo Installing missing dependencies...
    "%VENV_DIR%\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo ERROR: Failed to install requirements.txt.
        pause
        exit /b 1
    )
    "%VENV_DIR%\Scripts\python.exe" -m pip install pymysql
    if errorlevel 1 (
        echo ERROR: Failed to install pymysql.
        pause
        exit /b 1
    )
)

echo ========================================
echo   Local: http://127.0.0.1:23601
echo ========================================

:loop
echo.
echo Starting server...
"%VENV_DIR%\Scripts\python.exe" -m uvicorn web.app:app --host 127.0.0.1 --port 23601 --forwarded-allow-ips=127.0.0.1 --timeout-graceful-shutdown 60

echo Server exited, restarting in 3 seconds...
timeout /t 3 /nobreak >nul
goto loop
