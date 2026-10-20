@echo off
call "%~dp0run-youtube-clipping.cmd" --clips 4 --caption-styles studio pro colorized classic %*
exit /b %ERRORLEVEL%
