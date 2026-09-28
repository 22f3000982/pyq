@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (set "PYTHON=.venv\Scripts\python.exe") else (set "PYTHON=py -3")
%PYTHON% "scripts\start_release.py"
pause
