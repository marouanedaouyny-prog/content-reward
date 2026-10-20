@echo off
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -File "%~dp0start-youtube-clipping.ps1" -Selenium
if errorlevel 1 (
    echo.
    echo The clipping workflow could not start. Read the error above.
    pause
)
