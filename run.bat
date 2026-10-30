@echo off
setlocal
cd /d "%~dp0"
title Tonmakha BBQ - Quick Run

rem ---- 1) find Python (py or python) ----
set "PY="
where py >nul 2>nul && set "PY=py"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo [ERROR] Python not found. Install Python 3.10+ from python.org and tick "Add Python to PATH".
  pause
  exit /b 1
)

rem ---- 2) create .venv on first run ----
if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Creating virtual environment...
  %PY% -m venv .venv
  if errorlevel 1 goto :fail
)

rem ---- 3) install requirements on first run ----
if not exist ".venv\.deps_ok" (
  echo [2/3] Installing requirements ^(first run only, may take a few minutes^)...
  ".venv\Scripts\python.exe" -m pip install --upgrade pip -q
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto :fail
  echo ok> ".venv\.deps_ok"
)

rem ---- 4) create .env from example if missing ----
if not exist ".env" if exist ".env.example" copy ".env.example" ".env" >nul

rem ---- 5) start ----
echo [3/3] Starting Tonmakha BBQ ... ^(press Ctrl+C to stop^)
".venv\Scripts\python.exe" main.py
echo.
echo Server stopped.
pause
exit /b 0

:fail
echo.
echo [ERROR] Setup failed. Please read the messages above.
pause
exit /b 1
