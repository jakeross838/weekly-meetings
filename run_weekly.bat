@echo off
REM Ross Built — v2 Monday weekly automation.
REM Runs build_meeting_prep.py + validate_accountability.py and writes
REM state\LAST_RUN_STATUS.txt so Task Scheduler / human can confirm success.
REM
REM Cadence: weekly, Monday before 8am ET. Idempotent within an ISO week —
REM rerunning the same Monday updates the snapshot rather than appending.

setlocal EnableDelayedExpansion

cd /d "%~dp0"

if not exist "logs"  mkdir "logs"
if not exist "state" mkdir "state"

REM Timestamps via PowerShell — robust across direct + cmd /c invocations.
for /f "delims=" %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-ddTHH:mm:ss"') do set TS=%%i
for /f "delims=" %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set TSFILE=%%i

set STATUS_FILE=state\LAST_RUN_STATUS.txt
set LOG_FILE=logs\monday-run-%TSFILE%.log

(
  echo ========================================
  echo Ross Built v2 Monday automation
  echo Started: %TS%
  echo ========================================
) > "%LOG_FILE%"

echo [1/2] Building meeting-prep pages... >> "%LOG_FILE%"
python monday-binder\build_meeting_prep.py >> "%LOG_FILE%" 2>&1
set BUILD_RC=%ERRORLEVEL%
echo build_meeting_prep exit=%BUILD_RC% >> "%LOG_FILE%"

echo [2/2] Validating accountability loop... >> "%LOG_FILE%"
python validate_accountability.py >> "%LOG_FILE%" 2>&1
set VALIDATE_RC=%ERRORLEVEL%
echo validate_accountability exit=%VALIDATE_RC% >> "%LOG_FILE%"

REM Pull validate's status banner (OK ... or FIRST_RUN ...)
set BANNER=NO_BANNER
for /f "tokens=*" %%L in ('findstr /B /C:"OK iso_week=" /C:"FIRST_RUN iso_week=" "%LOG_FILE%"') do set BANNER=%%L

set OVERALL=PASS
if not "%BUILD_RC%"=="0"    set OVERALL=BUILD_FAIL
if not "%VALIDATE_RC%"=="0" set OVERALL=VALIDATE_FAIL

(
  echo last_run_at=%TS%
  echo overall=%OVERALL%
  echo build_meeting_prep_exit=%BUILD_RC%
  echo validate_accountability_exit=%VALIDATE_RC%
  echo banner=%BANNER%
  echo log_file=%LOG_FILE%
) > "%STATUS_FILE%"

echo Wrote %STATUS_FILE% >> "%LOG_FILE%"
type "%STATUS_FILE%"

if not "%OVERALL%"=="PASS" (
  echo MONDAY-RUN FAILED: %OVERALL% -- see %LOG_FILE%
  exit /b 1
)

echo MONDAY-RUN OK
exit /b 0
