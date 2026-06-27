@echo off
setlocal
title Stop NatureDrawImage Services

set "ROOT_DIR=%~dp0"
set "MYSQL_DIR_1=%ROOT_DIR%mysql-8.0.28-winx64"
set "MYSQL_DIR_2=%ROOT_DIR%..\mysql-8.0.28-winx64"

echo ========================================
echo  Stop NatureDrawImage gracefully
echo ========================================
echo.

echo [1/2] Web process
echo   If the Web terminal is open, press Ctrl+C there.
echo   In start-all.bat prompt: Y = close Web, N = graceful restart.
echo   This script will not force-kill Web, to avoid interrupting a running generation.
echo.

echo [2/2] Stop MySQL safely...
cd /d "%ROOT_DIR%"

if exist "%MYSQL_DIR_1%\stop_mysql.bat" (
    call "%MYSQL_DIR_1%\stop_mysql.bat" stop
    goto done
)

if exist "%MYSQL_DIR_2%\stop_mysql.bat" (
    call "%MYSQL_DIR_2%\stop_mysql.bat" stop
    goto done
)

echo   WARNING: stop_mysql.bat not found.
echo   Checked:
echo     %MYSQL_DIR_1%\stop_mysql.bat
echo     %MYSQL_DIR_2%\stop_mysql.bat
echo   Please stop MySQL manually if it is still running.

:done
echo.
echo Stop steps finished.
echo Redis is not required and was not touched.
pause
endlocal
