@echo off
REM One-time setup: finds Python, creates .venv, installs packages. Safe to run again.
cd /d "%~dp0"
if not exist "app.py" (
  echo ERROR: this file must sit in the project folder next to app.py.
  exit /b 1
)
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import streamlit, pydantic, fitz" 2>nul && exit /b 0
  ".venv\Scripts\python.exe" -m pip --version >nul 2>nul || (
    echo The existing .venv is incomplete; rebuilding it...
    rmdir /s /q .venv
  )
)
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY (
  echo ERROR: Python is not installed. Install Python 3.11 or newer from https://www.python.org/downloads/
  echo During install, tick "Add python.exe to PATH". Then double-click this file again.
  exit /b 1
)
echo Using: %PY%
%PY% --version
if not exist ".venv\Scripts\python.exe" (
  echo Creating the virtual environment - this can take 1-2 minutes with no output, do not press any keys...
  %PY% -m venv .venv || ( echo ERROR: could not create .venv & exit /b 1 )
)
echo Installing packages (a few minutes the first time)...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt || ( echo ERROR: package install failed, see the messages above & exit /b 1 )
echo Setup complete.
exit /b 0
