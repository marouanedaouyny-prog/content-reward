@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo The clipping environment is missing. Run setup-transcription.ps1 first.
    exit /b 2
)
"%~dp0.venv\Scripts\python.exe" -m clipping.autorun %*
exit /b %ERRORLEVEL%
