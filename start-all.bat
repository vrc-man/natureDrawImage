@echo off
setlocal
title NatureDrawImage Web

set "ROOT_DIR=%~dp0"
set "VENV_DIR=%ROOT_DIR%natureDrawImage-env"
set "MYSQL_DIR_1=%ROOT_DIR%mysql-8.0.28-winx64"
set "MYSQL_DIR_2=%ROOT_DIR%..\mysql-8.0.28-winx64"
set "ENV_FILE=%ROOT_DIR%.env"
set "MYSQL_PWD="

cd /d "%ROOT_DIR%"

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo ERROR: Virtual environment not found:
    echo   %VENV_DIR%
    echo Please create/install it first, or run start-Py64-311.bat.
    pause
    exit /b 1
)

if exist "%MYSQL_DIR_1%\bin\mysqld.exe" (
    set "MYSQL_DIR=%MYSQL_DIR_1%"
) else if exist "%MYSQL_DIR_2%\bin\mysqld.exe" (
    set "MYSQL_DIR=%MYSQL_DIR_2%"
) else (
    echo ERROR: MySQL portable directory not found.
    echo Checked:
    echo   %MYSQL_DIR_1%
    echo   %MYSQL_DIR_2%
    pause
    exit /b 1
)

if exist "%ENV_FILE%" (
    for /f "tokens=1,* delims==" %%a in ('findstr /b "MYSQL_PASSWORD=" "%ENV_FILE%"') do set "MYSQL_PWD=%%b"
)

echo ----------------------------------------
echo  Starting NatureDrawImage
echo  MySQL: %MYSQL_DIR%
echo  Web:   http://127.0.0.1:23601
echo  Redis: not required / not started
echo ----------------------------------------
echo.

call :ensure_mysql
if errorlevel 1 exit /b 1

:loop
echo.
echo ----------------------------------------
echo  Starting Web (port 23601, --reload)
echo  Press Ctrl+C to stop current Web process.
echo  After Ctrl+C: N = graceful restart, Y = close Web.
echo  MySQL stays running.
echo ----------------------------------------
"%VENV_DIR%\Scripts\python.exe" -m uvicorn web.app:app --host 127.0.0.1 --port 23601 --forwarded-allow-ips=127.0.0.1 --timeout-graceful-shutdown 60 --reload

echo.
echo Web stopped.
choice /c NY /n /m "N=graceful restart, Y=close Web: "
if errorlevel 2 goto exit
if errorlevel 1 goto restart

:restart
echo.
echo Graceful restarting Web...
goto loop

:exit
echo.
echo Web closed. MySQL is still running.
echo To stop MySQL safely, run stop-all.bat or:
echo   "%MYSQL_DIR%\stop_mysql.bat" stop
pause
exit /b 0

:ensure_mysql
echo [1/2] Check MySQL...
if defined MYSQL_PWD (
    "%MYSQL_DIR%\bin\mysqladmin.exe" -u root --protocol=TCP -h 127.0.0.1 --password=%MYSQL_PWD% ping >nul 2>&1
) else (
    "%MYSQL_DIR%\bin\mysqladmin.exe" -u root --protocol=TCP -h 127.0.0.1 ping >nul 2>&1
)
if %errorlevel% equ 0 (
    echo MySQL already running.
    exit /b 0
)

echo Starting MySQL...
start "MySQL" "%MYSQL_DIR%\bin\mysqld.exe" --defaults-file="%MYSQL_DIR%\my.ini" --console

set /a WAIT_COUNT=0
:wait_mysql
timeout /t 2 /nobreak >nul
set /a WAIT_COUNT+=1
if defined MYSQL_PWD (
    "%MYSQL_DIR%\bin\mysqladmin.exe" -u root --protocol=TCP -h 127.0.0.1 --password=%MYSQL_PWD% ping >nul 2>&1
) else (
    "%MYSQL_DIR%\bin\mysqladmin.exe" -u root --protocol=TCP -h 127.0.0.1 ping >nul 2>&1
)
if %errorlevel% equ 0 (
    echo MySQL ready.
    exit /b 0
)
if %WAIT_COUNT% geq 45 (
    echo ERROR: MySQL did not become ready in time.
    echo Please check the MySQL window or my.ini.
    pause
    exit /b 1
)
goto wait_mysql
