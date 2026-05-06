@echo off
REM Ross Built PM Weekly Processor
REM Double-click to run. Processes all transcripts in transcripts\inbox\

cd /d "%~dp0"

echo.
echo ========================================
echo  Ross Built PM Weekly Processor
echo ========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install from python.org and check "Add to PATH".
    pause
    exit /b 1
)

REM Check anthropic package
python -c "import anthropic" 2>nul
if errorlevel 1 (
    echo Installing anthropic package...
    python -m pip install anthropic
    if errorlevel 1 (
        echo ERROR: Could not install anthropic package.
        pause
        exit /b 1
    )
)

REM Run the processor
python process.py

REM Regenerate the one-click Monday binder so monday-binder.html stays fresh
echo.
python generate_monday_binder.py
if errorlevel 1 (
    echo WARN: monday-binder.html was not regenerated. Check generate_monday_binder.py.
) else (
    echo Monday binder regenerated -^> monday-binder.html
    REM Uncomment the next line to auto-open in the default browser after each run
    REM start "" "monday-binder.html"
)

echo.
echo ========================================
echo  Complete. Press any key to close.
echo ========================================
pause >nul
