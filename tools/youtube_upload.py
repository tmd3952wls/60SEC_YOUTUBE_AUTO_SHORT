"""YouTube Studio '60초쇼츠' (UCBG8sz9vJNT04OgkH5Z-OBw) 비공개(Private) 자동 업로드 도구.

- 전용 크롬 프로필(.vmake_chrome, 원격 포트 9333)을 재사용하며 다른 세션의 탭은 건드리지 않는다.
- 300MB+ 4K 영상도 전송 제한이 없도록 CDP DOM.setFileInputFiles 로 로컬 경로를 직접 지정한다.
- 로그인이 필요하거나 다른 채널 계정일 경우 창을 화면 앞으로 꺼내 사용자 로그인을 대기한다 (비밀번호 입력·우회 없음).

사용법:
  python -X utf8 tools/youtube_upload.py --video "C:/Users/.../퀵플립_4K.mp4" --name 퀵플립 --privacy private
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
TXT_DIR = Path.home() / "Downloads" / "chatgpt 사진"

CHANNEL_ID = "UCBG8sz9vJNT04OgkH5Z-OBw"
UPLOAD_URL = f"https://studio.youtube.com/channel/{CHANNEL_ID}/videos/upload?d=ud"

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
YT_CHROME_PROFILE = ROOT / ".yt_chrome"
CDP_PORT = 9335
HIDE_POS = (-32000, -32000)
SHOW_POS = (80, 40)


def parse_upload_txt(txt_path: Path) -> tuple[str, str, list[str]]:
    raw = txt_path.read_text(encoding="utf-8").strip()
    title = ""
    desc_lines: list[str] = []
    tags: list[str] = []
    mode = None
    for line in raw.splitlines():
        s = line.strip()
        if s.startswith("제목:"):
            title = s.split(":", 1)[1].strip()
            mode = "title"
        elif s.startswith("설명:"):
            rest = s.split(":", 1)[1].strip()
            if rest:
                desc_lines.append(rest)
            mode = "desc"
        elif s.startswith("태그:"):
            t_raw = s.split(":", 1)[1].strip()
            tags = [x.strip() for x in t_raw.split(",") if x.strip()]
            mode = "tags"
        else:
            if mode == "desc" and s:
                desc_lines.append(s)
    return title[:100], "\n".join(desc_lines).strip(), tags


def launch_or_attach(p, visible: bool = False):
    url = f"http://127.0.0.1:{CDP_PORT}"
    try:
        br = p.chromium.connect_over_cdp(url, timeout=3000)
        return br.contexts[0]
    except Exception:
        profile = YT_CHROME_PROFILE
        profile.mkdir(parents=True, exist_ok=True)
        # 세션 쿠키가 재시작 후에도 유지되도록 restore_on_startup=1 설정
        pref_file = profile / "Default" / "Preferences"
        if pref_file.exists():
            try:
                import json
                prefs = json.loads(pref_file.read_text(encoding="utf-8"))
                prefs.setdefault("session", {})["restore_on_startup"] = 1
                pref_file.write_text(json.dumps(prefs, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass
        x, y = SHOW_POS if visible else HIDE_POS
        subprocess.Popen([
            CHROME,
            f"--user-data-dir={profile}",
            f"--remote-debugging-port={CDP_PORT}",
            "--no-first-run",
            "--no-default-browser-check",
            "--window-size=1400,950",
            f"--window-position={x},{y}",
            "--disable-features=CalculateNativeWinOcclusion",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-background-timer-throttling",
            "about:blank",
        ])
        for _ in range(30):
            time.sleep(1)
            try:
                br = p.chromium.connect_over_cdp(url, timeout=3000)
                return br.contexts[0]
            except Exception:
                pass
        print("FAIL: 크롬 원격 디버깅 연결 실패", flush=True)
        sys.exit(7)


def move_window(ctx, page, show: bool = True):
    try:
        cdp = ctx.new_cdp_session(page)
        wid = cdp.send("Browser.getWindowForTarget")["windowId"]
        x, y = SHOW_POS if show else HIDE_POS
        cdp.send("Browser.setWindowBounds", {"windowId": wid, "bounds": {"windowState": "normal"}})
        cdp.send("Browser.setWindowBounds", {"windowId": wid, "bounds": {"left": x, "top": y}})
        if show:
            page.bring_to_front()
    except Exception as exc:
        print("창 이동 예외:", exc, flush=True)


def shot(page, dbg: Path, name: str):
    try:
        page.screenshot(path=str(dbg / f"{name}.png"))
    except Exception:
        pass


def ensure_studio_ready(ctx, page, dbg: Path):
    page.goto(UPLOAD_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(5000)

    def needs_user_auth() -> bool:
        u = page.url
        if "accounts.google.com" in u:
            return True
        txt = ""
        try:
            txt = page.inner_text("body")
        except Exception:
            pass
        bad_phrases = [
            "Oops, you don't have permission",
            "권한이 없습니다",
            "액세스 권한이 없습니다",
            "Switch account",
            "계정 전환",
        ]
        # If file input or upload button isn't present and permission error is shown
        has_file_input = page.locator("input[type=file]").count() > 0
        if not has_file_input and any(bp in txt for bp in bad_phrases):
            return True
        return False

    if needs_user_auth():
        shot(page, dbg, "00_auth_needed")
        print(
            "LOGIN_NEEDED: 화면에 열린 크롬 창에서 '60초쇼츠' 유튜브(구글) 계정으로 로그인/계정 전환해 주세요 (최대 10분 대기)",
            flush=True,
        )
        move_window(ctx, page, show=True)
        t0 = time.time()
        while time.time() - t0 < 600:
            page.wait_for_timeout(3000)
            if not needs_user_auth() and "studio.youtube.com" in page.url:
                if CHANNEL_ID not in page.url:
                    page.goto(UPLOAD_URL, wait_until="domcontentloaded")
                    page.wait_for_timeout(4000)
                if not needs_user_auth():
                    break
        else:
            shot(page, dbg, "00_auth_timeout")
            print("FAIL: 유튜브 로그인 대기 시간 초과", flush=True)
            sys.exit(6)
        move_window(ctx, page, show=False)

    # Ensure upload dialog file input is present (if upload modal didn't auto-open, click Create -> Upload)
    if page.locator("input[type=file]").count() == 0:
        for sel in ["ytcp-button#create-icon", "#upload-icon", "ytcp-icon-button#upload-icon"]:
            if page.locator(sel).count():
                try:
                    page.locator(sel).first.click(timeout=3000)
                    page.wait_for_timeout(1500)
                    break
                except Exception:
                    pass
        for txt in ["동영상 업로드", "Upload videos", "Upload video"]:
            loc = page.get_by_text(txt, exact=False)
            if loc.count():
                try:
                    loc.first.click(timeout=3000)
                    page.wait_for_timeout(2000)
                    break
                except Exception:
                    pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True, help="업로드할 mp4 경로")
    ap.add_argument("--name", required=True, help="업로드정보 txt 앞 한글 이름 (예: 퀵플립)")
    ap.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"])
    ap.add_argument("--dry", action="store_true", help="저장 직전에 멈춤")
    ap.add_argument("--timeout-min", type=float, default=30)
    a = ap.parse_args()

    video = Path(a.video)
    if not video.is_absolute() and not video.exists():
        video = TXT_DIR / a.video
    video = video.resolve()
    if not video.exists():
        raise SystemExit(f"영상 파일이 없습니다: {video}")

    info_path = TXT_DIR / f"{a.name}_업로드정보(제목·설명·태그).txt"
    title, desc, tags = parse_upload_txt(info_path)
    if not title:
        raise SystemExit(f"제목을 찾지 못했습니다: {info_path}")

    dbg = ROOT / "jobs" / "_yt_upload_debug" / a.name
    dbg.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        ctx = launch_or_attach(p)
        page = ctx.new_page()
        try:
            ensure_studio_ready(ctx, page, dbg)
            page.locator("input[type=file]").first.wait_for(state="attached", timeout=30000)
            shot(page, dbg, "01_studio_ready")

            # Attach large 4K file directly via CDP DOM.setFileInputFiles
            cdp = ctx.new_cdp_session(page)
            doc = cdp.send("DOM.getDocument", {"depth": 0})["root"]["nodeId"]
            fnode = cdp.send("DOM.querySelector", {"nodeId": doc, "selector": "input[type=file]"})["nodeId"]
            cdp.send("DOM.setFileInputFiles", {"nodeId": fnode, "files": [str(video)]})
            print(f"파일 선택 완료: {video.name} ({video.stat().st_size / 1e6:.1f} MB)", flush=True)

            # Wait for metadata form (#title-textarea)
            title_box = page.locator("ytcp-social-suggestions-textbox#title-textarea div#textbox").first
            title_box.wait_for(state="visible", timeout=60000)
            page.wait_for_timeout(2000)
            shot(page, dbg, "02_form_opened")

            # 1. Title
            title_box.click()
            page.keyboard.press("Control+A")
            page.keyboard.press("Backspace")
            page.keyboard.insert_text(title)
            page.wait_for_timeout(600)

            # 2. Description
            desc_box = page.locator("ytcp-social-suggestions-textbox#description-textarea div#textbox").first
            desc_box.click()
            page.keyboard.press("Control+A")
            page.keyboard.press("Backspace")
            page.keyboard.insert_text(desc)
            page.wait_for_timeout(600)

            # 3. Not made for kids
            mfk = page.locator('tp-yt-paper-radio-button[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"]').first
            mfk.scroll_into_view_if_needed()
            mfk.click()
            page.wait_for_timeout(500)

            # 4. Show more -> Altered content = No + Tags
            toggle = page.locator("ytcp-button#toggle-button").first
            if toggle.is_visible():
                toggle.scroll_into_view_if_needed()
                toggle.click()
                page.wait_for_timeout(1000)

            alt_no = page.locator('tp-yt-paper-radio-button[name="VIDEO_HAS_ALTERED_CONTENT_NO"]')
            if alt_no.count() and alt_no.first.is_visible():
                alt_no.first.scroll_into_view_if_needed()
                alt_no.first.click()
                page.wait_for_timeout(400)

            if tags:
                tag_input = page.locator("ytcp-form-input-container#tags-container input#text-input").first
                if tag_input.count():
                    tag_input.scroll_into_view_if_needed()
                    tag_input.click()
                    page.keyboard.insert_text(", ".join(tags) + ",")
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(600)

            shot(page, dbg, "03_details_filled")
            print(f"메타데이터 입력 완료: '{title}' (태그 {len(tags)}개)", flush=True)

            # Grab video URL if already assigned
            video_url = ""
            link_loc = page.locator("a.style-scope.ytcp-video-info")
            if link_loc.count():
                video_url = link_loc.first.get_attribute("href") or ""

            # 5. Click Next x3 to reach Visibility step
            for step_idx in range(3):
                nxt = page.locator("ytcp-button#next-button").first
                nxt.wait_for(state="visible", timeout=15000)
                nxt.click()
                page.wait_for_timeout(1200)

            # 6. Select Privacy radio button
            priv_map = {
                "private": "PRIVATE",
                "unlisted": "UNLISTED",
                "public": "PUBLIC",
            }
            priv_radio = page.locator(f'tp-yt-paper-radio-button[name="{priv_map[a.privacy]}"]').first
            priv_radio.wait_for(state="visible", timeout=15000)
            priv_radio.click()
            page.wait_for_timeout(800)
            shot(page, dbg, "04_visibility_selected")

            if not video_url and link_loc.count():
                video_url = link_loc.first.get_attribute("href") or ""

            # 7. Wait until raw file upload reaches 100% BEFORE clicking Save or closing tab!
            # Korean UI shows "31% 업로드 중", English UI shows "Uploading 31%"
            def is_still_uploading() -> tuple[bool, str]:
                txts = []
                for sel in ["ytcp-video-upload-progress", "ytcp-uploads-still-processing-dialog", "tp-yt-paper-dialog"]:
                    loc = page.locator(sel)
                    for i in range(loc.count()):
                        try:
                            if loc.nth(i).is_visible():
                                txts.append(loc.nth(i).inner_text())
                        except Exception:
                            pass
                joined = " | ".join(txts)
                busy = bool(re.search(r"(\d+%\s*업로드|Uploading\s*\d+%|동영상 업로드 중|아직 업로드하는 중|업로드 중\s*\.\.\.)", joined, re.I))
                return busy, joined.replace("\n", " ")[:120]

            deadline = time.time() + a.timeout_min * 60
            tick = 0
            while time.time() < deadline:
                still_up, status_line = is_still_uploading()
                done_btn = page.locator("ytcp-button#done-button").first
                disabled = done_btn.get_attribute("disabled") is not None
                if not still_up and not disabled:
                    break
                tick += 1
                if tick % 3 == 0:
                    print(f"  ..파일 전송 중 ({status_line})", flush=True)
                    shot(page, dbg, f"up_{tick:03d}")
                page.wait_for_timeout(4000)
            else:
                shot(page, dbg, "timeout_upload")
                print("FAIL: 유튜브 파일 업로드 대기 시간 초과", flush=True)
                sys.exit(5)

            if not video_url and link_loc.count():
                video_url = link_loc.first.get_attribute("href") or ""

            if a.dry:
                print(f"DRY: 저장 직전에 멈춤 (URL={video_url})", flush=True)
                return

            page.locator("ytcp-button#done-button").first.click()
            page.wait_for_timeout(5000)

            # Double-check post-save dialog: if YouTube still says "비공개 동영상을 아직 업로드하는 중입니다", wait until it finishes!
            while time.time() < deadline:
                still_up, status_line = is_still_uploading()
                if not still_up:
                    break
                print(f"  ..저장 후 전송 마무리 대기 ({status_line})", flush=True)
                page.wait_for_timeout(4000)

            shot(page, dbg, "05_saved")

            # Close share/processing dialog if shown
            for close_sel in ["ytcp-button#close-button", "ytcp-icon-button#close-button"]:
                if page.locator(close_sel).count() and page.locator(close_sel).first.is_visible():
                    try:
                        page.locator(close_sel).first.click(timeout=2000)
                        break
                    except Exception:
                        pass

            print(f"UPLOAD_DONE: [{a.privacy.upper()}] {title} -> {video_url}", flush=True)
        finally:
            if not a.dry:
                try:
                    page.close()
                except Exception:
                    pass


if __name__ == "__main__":
    main()
