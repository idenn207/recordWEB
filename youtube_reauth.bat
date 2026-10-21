@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist "tools\.venv\Scripts\python.exe" (
    python -m venv "tools\.venv"
    if errorlevel 1 goto failed
)
"tools\.venv\Scripts\python.exe" -c "import google_auth_oauthlib" >nul 2>&1
if errorlevel 1 (
    "tools\.venv\Scripts\python.exe" -m pip install -r "tools\requirements-youtube.txt"
    if errorlevel 1 goto failed
)
"tools\.venv\Scripts\python.exe" "tools\youtube_reauth.py" --nas-url "http://192.168.0.10:5080" %*
if errorlevel 1 goto failed
echo.
echo Reauthentication completed. You can close this window.
pause
exit /b 0
:failed
echo.
echo Reauthentication failed. Review the message above and try again.
pause
exit /b 1
