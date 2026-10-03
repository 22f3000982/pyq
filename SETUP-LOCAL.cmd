@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (echo Install Python 3.11 or 3.12 from python.org first. & pause & exit /b 1)
if not exist ".venv\Scripts\python.exe" py -3 -m venv .venv
if errorlevel 1 (pause & exit /b 1)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (pause & exit /b 1)
echo Setup complete. Double-click START-LOCAL.cmd.
pause
