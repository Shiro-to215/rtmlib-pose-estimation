@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Python environment not found. Follow the Windows setup in README.md.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" "gui.py"
if errorlevel 1 (
    echo Application failed. Check the error above.
    pause
    exit /b 1
)
