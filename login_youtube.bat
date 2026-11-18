@echo off
chcp 65001 >nul
echo [60초쇼츠] 유튜브 스튜디오 전용 크롬 창을 엽니다.
echo 로그인 완료 후 유튜브 스튜디오 화면이 보이면 크롬 창을 닫아주세요!
"C:\Program Files\Google\Chrome\Application\chrome.exe" --user-data-dir="C:\Users\tmd39\Desktop\60SEC_YOUTUBE_AUTO_SHORT\.yt_chrome" --no-first-run --no-default-browser-check "https://studio.youtube.com/channel/UCBG8sz9vJNT04OgkH5Z-OBw"
