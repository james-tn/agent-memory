@echo off
echo ============================================
echo   Agent Memory Service - Interactive Demo
echo ============================================
echo.
echo Starting Streamlit demo...
echo.
echo The demo will open in your default browser.
echo Press Ctrl+C to stop the demo.
echo.
echo ============================================
echo.

cd /d "%~dp0.."
uv run streamlit run demo\interactive_demo_live.py --server.port 8501 --server.headless false

pause
