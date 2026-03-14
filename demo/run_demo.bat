@echo off
cd /d %~dp0..
echo Running demo...
uv run python demo/05_server_mode.py --scripted
pause
