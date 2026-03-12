@echo off
setlocal

REM Change to the folder where this .bat lives
cd /d "%~dp0"

echo Running Shinylive build...
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_shinylive.ps1"
if ERRORLEVEL 1 (
    echo.
    echo Shinylive build FAILED.
    pause
    exit /b 1
) else (
    echo.
    echo Shinylive build COMPLETED successfully.
    pause
    exit /b 0
)
