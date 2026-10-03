@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (echo Run SETUP-LOCAL.cmd first. & pause & exit /b 1)
.venv\Scripts\python.exe tools\local_preview.py
pause
