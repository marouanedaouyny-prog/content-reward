@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo The clipping environment is missing. Run setup-transcription.ps1 first.
    pause
    exit /b 2
)
if /I "%~1"=="--resume" goto saved_order
if /I "%~1"=="--status" goto saved_order
if /I "%~1"=="--help" goto saved_order
echo Starting a fresh search for distinct clips with colorized captions.
echo Only selected video windows are downloaded. Publishing is disabled.
"%~dp0.venv\Scripts\python.exe" -m clipping.orchestrator --clips 20 --per-source 20 --caption-style colorized --framing fit --provider public %*
goto finished
:saved_order
"%~dp0.venv\Scripts\python.exe" -m clipping.orchestrator %*
:finished
set "clip_workflow_exit=%ERRORLEVEL%"
if not "%clip_workflow_exit%"=="0" goto failed
if /I "%~1"=="--status" goto done
if /I "%~1"=="--help" goto done
echo Open clips\LATEST-CLIPS.txt to find the newest completed batch.
start "" explorer.exe "%~dp0clips"
goto done
:failed
echo If an order was created, resume it with: make-20-clips.cmd --resume ORDER_ID
echo The status above gives the order ID and any connection or source limit.
:done
pause
exit /b %clip_workflow_exit%
