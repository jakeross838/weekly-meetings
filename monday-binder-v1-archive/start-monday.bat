@echo off
REM Monday Binder launcher.
REM Double-click to start the local server + open the binder in the default browser.
REM Keep this console window open. Close it to stop the server.

cd /d "%~dp0"

REM If another process is already listening on 8765, just open the browser.
netstat -ano | find "127.0.0.1:8765" | find "LISTENING" >nul
if %errorlevel%==0 (
    echo Monday Binder server is already running on port 8765.
    echo Opening browser...
    start "" "http://localhost:8765"
    exit /b 0
)

echo ========================================
echo  Starting Monday Binder server
echo ========================================
echo  URL:  http://localhost:8765
echo  Keep this window open. Close it to stop.
echo ========================================
echo.

REM Open the browser shortly after the server starts.
start "" cmd /c "timeout /t 2 /nobreak >nul & start """" ""http://localhost:8765"""

REM Run the server in the foreground.
python server.py

echo.
echo Server exited. Press any key to close this window.
pause >nul
