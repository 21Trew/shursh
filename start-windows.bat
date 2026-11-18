@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if %errorlevel%==0 (
  echo Starting Shursh on http://127.0.0.1:8787
  start "" "http://127.0.0.1:8787"
  py -3 server.py
) else (
  where python >nul 2>&1
  if %errorlevel%==0 (
    start "" "http://127.0.0.1:8787"
    python server.py
  ) else (
    echo Python 3.10+ is required. Install it from python.org
    pause
    exit /b 1
  )
)
pause
