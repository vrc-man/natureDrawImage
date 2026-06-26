@echo off
title NatureDrawImage
set "ROOT_DIR=%~dp0"
set "MYSQL_DIR=%ROOT_DIR%..\mysql-8.0.28-winx64"
set "VENV_DIR=%ROOT_DIR%natureDrawImage-env"
cd /d "%ROOT_DIR%"

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo ERROR: Virtual environment not found:
    echo   %VENV_DIR%
    echo Please create/install it first, or run start-Py64-311.bat.
    pause
    exit /b 1
)

if /i "%1"=="stop" goto stop
if /i "%1"=="restart" goto restart

:start
echo Starting Web (MySQL must be running first)...
"%VENV_DIR%\Scripts\python.exe" -m uvicorn web.app:app --host 127.0.0.1 --port 23601 --forwarded-allow-ips=127.0.0.1 --timeout-graceful-shutdown 60 --reload

echo Web stopped.
pause
exit /b

:restart
echo Restarting Web...
"%VENV_DIR%\Scripts\python.exe" -m uvicorn web.app:app --host 127.0.0.1 --port 23601 --forwarded-allow-ips=127.0.0.1 --timeout-graceful-shutdown 60 --reload
pause
exit /b

:stop
echo Are you sure you want to stop the Web server? (y/n)
set /p confirm=
if /i not "%confirm%"=="y" (
    echo Cancelled.
    pause
    exit /b
)
echo Stopping Web via Ctrl+C in current session...
exit /b
