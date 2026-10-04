@echo off
cd /d "%~dp0"
py -3 -m venv .venv
if errorlevel 1 goto failed
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto failed
if not exist local.env copy .env.example local.env >nul
echo Edit local.env, then run START_AI_WORKER.cmd.
pause
exit /b 0
:failed
echo Setup failed. Install Python 3 and retry.
pause
exit /b 1
