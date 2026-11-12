"""네이버 메일 '내게쓰기' 자동 발송 (2026-11-11).

.env 에 NAVER_SMTP_USER(아이디, @naver.com 빼고) / NAVER_SMTP_PASS(애플리케이션 비밀번호) 필요.
받는 사람 = 보내는 사람(본인). 비밀번호는 화면에 절대 출력하지 않음.

python tools/send_mail.py --job cardboard --video full_v9.mp4 --name 페이퍼박스
  - 본문: Downloads\\chatgpt 사진\\<이름>_업로드정보(제목·설명·태그).txt + <이름>_고정댓글.txt 내용
  - 첨부: 영상 파일만 (txt 는 첨부하지 않음)
"""
import argparse
import re
import smtplib
import subprocess
import ssl
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TXT_DIR = Path.home() / "Downloads" / "chatgpt 사진"


def env(key):
    s = (ROOT / ".env").read_text(encoding="utf-8")
    m = re.search(rf"^{key}=(.*)$", s, re.M)
    v = m.group(1).strip().strip('"').strip("'") if m else ""
    if not v:
        raise SystemExit(f".env 에 {key} 가 비어 있어요")
    return v


MAX_MB = 24.0  # 네이버 SMTP: 25MB 는 통과, 30.7MB 는 552 거절 (2026-11-11 실측)


def fit_size(video):
    """너무 크면 메일용 사본(<이름>_mail.mp4)을 만들어 반환. 원본은 그대로."""
    if video.stat().st_size / 1e6 <= MAX_MB:
        return video
    out = video.with_name(video.stem + "_mail.mp4")
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                str(video)], capture_output=True, text=True, check=True).stdout)
    vk = int((MAX_MB - 1.5) * 8000 / dur) - 192  # 목표 크기에 맞춘 영상 kbps (음성 192k 제외)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-c:v", "libx264", "-preset", "slow",
                    "-b:v", f"{vk}k", "-maxrate", f"{int(vk * 1.3)}k", "-bufsize", f"{vk * 2}k",
                    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)], check=True)
    print(f"메일용 사본: {out.name} ({video.stat().st_size / 1e6:.1f}MB → {out.stat().st_size / 1e6:.1f}MB)")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True)
    ap.add_argument("--video", required=True)
    ap.add_argument("--name", required=True, help="txt 파일 앞 한글 이름 (예: 페이퍼박스)")
    a = ap.parse_args()

    user = env("NAVER_SMTP_USER").split("@")[0]
    pw = env("NAVER_SMTP_PASS")
    addr = f"{user}@naver.com"

    info = (TXT_DIR / f"{a.name}_업로드정보(제목·설명·태그).txt").read_text(encoding="utf-8").strip()
    pinned = (TXT_DIR / f"{a.name}_고정댓글.txt").read_text(encoding="utf-8").strip()
    title = next((l.split(":", 1)[1].strip() for l in info.splitlines() if l.startswith("제목:")), a.name)

    video = ROOT / "jobs" / a.job / a.video
    video = fit_size(video)
    msg = EmailMessage()
    msg["From"] = addr
    msg["To"] = addr
    msg["Subject"] = f"[60초쇼츠] {title}"
    msg.set_content(
        "■ 업로드 정보 (제목·설명·태그)\n" + "─" * 30 + "\n" + info
        + "\n\n\n■ 고정댓글\n" + "─" * 30 + "\n" + pinned + "\n"
    )
    msg.add_attachment(video.read_bytes(), maintype="video", subtype="mp4", filename=video.name)

    with smtplib.SMTP_SSL("smtp.naver.com", 465, context=ssl.create_default_context(), timeout=300) as s:
        s.login(user, pw)
        s.send_message(msg)
    print(f"보냄: {addr} ← '{msg['Subject']}' (첨부 {video.name}, {video.stat().st_size / 1e6:.1f}MB)")


if __name__ == "__main__":
    main()
