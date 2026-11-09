@echo off
chcp 65001 >nul
cd /d "%~dp0"
python editor\server.py
pause
