@echo off
echo ============================================
echo  Defense Fire Protection - Takeoff Tool
echo  Installing dependencies...
echo ============================================

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.9+ from https://python.org
    pause
    exit /b 1
)

pip install -r requirements.txt

echo.
echo ============================================
echo  Launching Takeoff Tool...
echo ============================================
python main.py
pause
