@echo off
setlocal ENABLEDELAYEDEXPANSION

set SCRIPT_DIR=%~dp0
set MAIN_SCRIPT=%SCRIPT_DIR%main.py

echo ============================================
echo   OpenCore Prodigy - Windows Launcher
echo ============================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo Python is not installed or not in PATH.
    echo Please install Python 3 and try again.
    echo.
    pause
    exit /b 1
)

if not exist "%MAIN_SCRIPT%" (
    echo Could not find main.py in:
    echo %SCRIPT_DIR%
    echo.
    pause
    exit /b 1
)

echo Launching OpenCore Prodigy...
echo.
python "%MAIN_SCRIPT%"
echo.
pause
endlocal
