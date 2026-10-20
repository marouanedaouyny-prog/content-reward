@echo off
cd /d "%~dp0"
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo Run setup-transcription.ps1 first to install the clipping environment.
    exit /b 1
)
"%~dp0.venv\Scripts\python.exe" -m clipping --ishowspeed
