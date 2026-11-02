@echo off
setlocal
where wsl.exe >nul 2>nul
if errorlevel 1 (
  echo WSL2 is required. See README.md for installation and prerequisites.
  pause
  exit /b 1
)
rem --cd accepts a Windows path; trailing dot avoids trailing-backslash quoting.
wsl.exe --cd "%~dp0." -- bash ./start-linux.sh
set "result=%errorlevel%"
if not "%result%"=="0" pause
exit /b %result%
