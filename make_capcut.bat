@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo EDL 을 CapCut 프로젝트로 만듭니다. (CapCut 을 꺼 두면 목록에 바로 등록됩니다)
echo.
dir /b jobs
echo.
set /p JOB=작업 이름:
dir /b "jobs\%JOB%\v*_edl.json"
set /p EDL=편집본 파일 (예: v5_edl.json):
python -m shorts.capcut --job "%JOB%" --edl "%EDL%"
pause
