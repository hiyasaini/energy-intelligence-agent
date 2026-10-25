@echo off
REM Double-click to rehearse the agent on the five NIFTY 50 Track B companies.
cd /d "%~dp0"
call "%~dp0setup.bat" || goto :fail
echo.
echo Running the tests...
".venv\Scripts\python.exe" -m pytest -q
echo.
echo Starting the dry run (10-20 minutes)...
".venv\Scripts\python.exe" scripts\dry_run.py %*
goto :end
:fail
echo.
echo Setup did not finish. Take a screenshot of this window and send it.
:end
pause
