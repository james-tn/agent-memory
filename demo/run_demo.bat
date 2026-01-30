@echo off
cd /d %~dp0..
echo Running demo...
uv run python demo/04_financial_advisor_remote.py --scripted
pause
