@echo off
setlocal

cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
    echo Python Launcher was not found. Install Python 3.12 and run this script again.
    exit /b 1
)

echo Creating .venv with Python 3.12...
py -3.12 -m venv .venv
if errorlevel 1 exit /b 1

echo Installing runtime and development dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m pip install -r requirements.txt -r requirements-dev.txt
if errorlevel 1 exit /b 1

set "PLOTLY_FILE=web\vendor\plotly-2.24.1.min.js"
set "PLOTLY_URL=https://cdn.plot.ly/plotly-2.24.1.min.js"
set "PLOTLY_SHA256=d5dae4bdea4f17da17c819b04f7ddcf05e3cffd252194cbe89cbbff40ee1d3c7"

if not exist "web\vendor" mkdir "web\vendor"
if not exist "%PLOTLY_FILE%" (
    echo Downloading Plotly.js 2.24.1...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -UseBasicParsing -Uri '%PLOTLY_URL%' -OutFile '%PLOTLY_FILE%'"
    if errorlevel 1 exit /b 1
)

echo Verifying Plotly.js SHA-256...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$actual=(Get-FileHash -Algorithm SHA256 -LiteralPath '%PLOTLY_FILE%').Hash.ToLowerInvariant(); if ($actual -ne '%PLOTLY_SHA256%') { Write-Error ('Unexpected SHA-256: ' + $actual); exit 1 }"
if errorlevel 1 exit /b 1

echo Setup complete. Start the application with run_app.bat.
