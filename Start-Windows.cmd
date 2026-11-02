@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "tools\portable.py" %*
) else (
  where py >nul 2>nul
  if errorlevel 1 (
    python "tools\portable.py" %*
  ) else (
    py -3 "tools\portable.py" %*
  )
)
set "result=%errorlevel%"
if not "%result%"=="0" (
  echo Startup failed. Install native Python 3.10+ with pip/venv; see README.md.
  pause
)
exit /b %result%
