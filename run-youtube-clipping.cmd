@echo off
cd /d "%~dp0"
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo The clipping environment is missing. Run setup-transcription.ps1 first.
    pause
    exit /b 2
)
"%~dp0.venv\Scripts\python.exe" -m clipping.orchestrator %*
set "clipping_exit_code=%ERRORLEVEL%"
if "%clipping_exit_code%"=="75" echo Connection unavailable. Progress is saved. Resume with run-youtube-clipping.cmd --resume latest
if "%clipping_exit_code%"=="0" echo Controller finished. Read the status and file paths above.
pause
exit /b %clipping_exit_code%
