@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo CapCut 을 완전히 끈 상태에서 실행하세요. 만들어 둔 프로젝트를 CapCut 목록에 등록합니다.
python -m shorts.capcut --register-only
pause
