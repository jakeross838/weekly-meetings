@echo off
REM Ross Built Monday Ops — start the unified dashboard.
REM Localhost-only Flask app on http://localhost:8765.
REM Keep this console window open. Close it to stop the server.

cd /d "%~dp0"

echo.
echo ========================================
echo   Ross Built Monday Ops
echo   http://localhost:8765
echo ========================================
echo.
echo Starting Flask server. Browser will open in 2 seconds.
echo Close this window to stop the server.
echo.

REM Open the browser after a short delay so the server has time to bind.
start "" /min cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:8765"

python monday-binder\transcript-ui\server.py
