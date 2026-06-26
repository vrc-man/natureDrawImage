@echo off
title Init Database
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

echo [1/3] Check MySQL...
"%MYSQL_DIR%\bin\mysqladmin" -u root --protocol=TCP -h 127.0.0.1 ping >nul 2>&1
if %errorlevel% neq 0 (
    echo Starting MySQL...
    start "MySQL" "%MYSQL_DIR%\bin\mysqld" --defaults-file="%MYSQL_DIR%\my.ini" --console
    :wait_mysql
    timeout /t 2 /nobreak >nul
    "%MYSQL_DIR%\bin\mysqladmin" -u root --protocol=TCP -h 127.0.0.1 ping >nul 2>&1
    if errorlevel 1 goto wait_mysql
    echo MySQL ready
) else (
    echo MySQL already running
)

echo [2/3] Create database...
"%MYSQL_DIR%\bin\mysql" -u root --protocol=TCP -h 127.0.0.1 -e "CREATE DATABASE IF NOT EXISTS natureDrawImage CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

echo [3/3] Initialize tables (start web)...
echo Starting web to auto-create tables. Wait for [schema] message then Ctrl+C.
echo.
pause
"%VENV_DIR%\Scripts\python.exe" -m uvicorn web.app:app --host 127.0.0.1 --port 23601

echo Done. You can now run start-all.bat to use the app.
echo If you need to import old data, run the sync tool.
pause
