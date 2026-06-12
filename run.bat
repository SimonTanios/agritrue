@echo off
REM ===================================================================
REM  AgriTrue - one-click launcher (Windows)
REM  Creates an isolated virtual environment, installs dependencies,
REM  generates the seed dataset, runs the tests, and launches the app.
REM ===================================================================
setlocal
cd /d "%~dp0"

echo.
echo [AgriTrue] Setting up environment...
if not exist ".venv\" (
    python -m venv .venv
)
call .venv\Scripts\activate.bat

echo [AgriTrue] Installing dependencies (first run only)...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

echo [AgriTrue] Generating seed dataset...
python -m tca.data_pipeline

echo [AgriTrue] Running tests...
python tests\test_engine.py
if errorlevel 1 (
    echo [AgriTrue] Engine tests failed - aborting.
    pause
    exit /b 1
)
python tests\test_features.py
if errorlevel 1 (
    echo [AgriTrue] Feature tests failed - aborting.
    pause
    exit /b 1
)

echo.
echo [AgriTrue] Launching dashboard at http://localhost:8501 ...
echo            (Press Ctrl+C in this window to stop.)
echo.
streamlit run app.py

endlocal
