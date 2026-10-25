@echo off
REM Double-click to start the Energy Intelligence Agent dashboard.
cd /d "%~dp0"
call "%~dp0setup.bat" || goto :fail
echo.
echo Starting the dashboard... it opens in your browser. Keep this window open; close it to stop the app.
".venv\Scripts\python.exe" -m streamlit run app.py
goto :end
:fail
echo.
echo Setup did not finish. Take a screenshot of this window and send it.
:end
pause
