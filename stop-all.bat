@echo off
setlocal
title Stop All Services

set "ROOT_DIR=%~dp0"
set "MYSQL_DIR_1=%ROOT_DIR%mysql-8.0.28-winx64"
set "MYSQL_DIR_2=%ROOT_DIR%..\mysql-8.0.28-winx64"

echo ========================================
echo  Shutting down all services gracefully
echo ========================================
echo.

echo [1/3] Notify Web process...
echo   If the Web terminal is open, press Ctrl+C there.
echo   If needed, close the Web window manually.
echo.

echo [2/3] Try graceful Web API shutdown...
powershell -NoProfile -Command "try { Invoke-WebRequest -Uri 'http://127.0.0.1:23601/api/admin/graceful-restart' -Method POST -Headers @{'Content-Type'='application/json'} -Body '{}' -TimeoutSec 5 | Out-Null; Write-Host '  Web shutdown signal sent.' } catch { Write-Host '  Web not responding, skipped.' }" 2>nul

timeout /t 2 /nobreak >nul

echo.
echo [3/3] Stop MySQL safely...
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
echo All stop steps finished. It is safe to close this window.
pause
endlocal
