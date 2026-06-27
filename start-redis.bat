@echo off
title Redis Server
set "REDIS_DIR=I:\cc\redis"
cd /d "%REDIS_DIR%"
echo Starting Redis on port 6379...
redis-server.exe redis.windows.conf
echo.
echo Redis stopped.
pause
