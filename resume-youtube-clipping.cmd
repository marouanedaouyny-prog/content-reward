@echo off
call "%~dp0run-youtube-clipping.cmd" --resume latest %*
exit /b %ERRORLEVEL%
