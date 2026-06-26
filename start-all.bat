@echo off
title NatureDrawImage Web
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

echo ----------------------------------------
echo  Starting Web (port 23601, --reload)
echo  MySQL stays running
echo ----------------------------------------

:loop
"%VENV_DIR%\Scripts\python.exe" -m uvicorn web.app:app --host 127.0.0.1 --port 23601 --forwarded-allow-ips=127.0.0.1 --timeout-graceful-shutdown 60 --reload

echo.
echo Web stopped.
choice /c YN /n /m "Restart Web? N=restart Y=exit: "
if errorlevel 2 goto restart
if errorlevel 1 goto exit

:restart
echo.
echo Restarting Web...
goto loop

:exit
echo.
echo Exiting. MySQL is still running.
echo To stop MySQL safely: stop_mysql.bat stop
pause
