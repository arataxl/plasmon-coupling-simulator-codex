@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo .venv was not found. Run setup_windows.bat first.
    exit /b 1
)

echo Starting Plasmonic Coupling Simulator at http://127.0.0.1:8000/
".venv\Scripts\python.exe" -m uvicorn src.main:app --host 127.0.0.1 --port 8000
