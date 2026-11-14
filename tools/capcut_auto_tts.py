"""CapCut '활기찬 바리톤' (vibrant_baritone, 1.1x) 완전 자동 GUI 음성 합성 + 수확 도구.

왜 PIL.ImageGrab / win32gui.EnumWindows 대신 이 스크립트를 쓰는가:
- Windows에서 PIL.ImageGrab.grab() (GetDC(NULL))은 디스플레이 컨텍스트에 따라 OSError가 날 수 있고,
  pywin32의 win32gui.EnumWindows는 권한 높은 시스템 창에서 GetLastError()==5가 남아 예외를 던집니다.
  (이는 agy 샌드박스 차단이 아닙니다!)
- 대신 CapCut.exe를 QSG_RHI_BACKEND=opengl, QT_OPENGL=software로 실행한 뒤
  ctypes.windll.user32.EnumWindows + PrintWindow(hwnd, mfcDC, 2) + PostMessageW를 사용하면
  사용자가 직접 클릭하지 않아도 100% 자동으로 '활기찬 바리톤' 음성을 생성하고 수확할 수 있습니다.

사용법:
  python -X utf8 tools/capcut_auto_tts.py --job bugbitething --edl v1_edl.json
"""
import argparse
import ctypes
import ctypes.wintypes
import json
import os
import subprocess
import sys
import time
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

from shorts.common import ASSETS, JOBS, read_json  # noqa: E402
from tools.capcut_voice import harvest, key, lines_of, make  # noqa: E402

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    ctypes.windll.user32.SetProcessDPIAware()

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

WM_ACTIVATE = 0x0006
WM_SETFOCUS = 0x0007
WM_CLOSE = 0x0010
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_CHAR = 0x0102
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
MK_LBUTTON = 0x0001


def makelparam(lo, hi):
    return ((hi & 0xFFFF) << 16) | (lo & 0xFFFF)


def resolve_capcut_exe() -> str:
    apps = Path(r"C:\Users\tmd39\AppData\Local\CapCut\Apps")
    preferred = apps / "9.7.1.4203" / "CapCut.exe"
    if preferred.exists():
        return str(preferred)
    cands = []
    for d in apps.iterdir():
        if d.is_dir() and (d / "CapCut.exe").exists():
            parts = [int(x) for x in d.name.split(".") if x.isdigit()]
            cands.append((parts, str(d / "CapCut.exe")))
    if cands:
        cands.sort(reverse=True)
        return cands[0][1]
    return str(apps / "CapCut.exe")


def find_capcut_windows():
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    found = []

    def cb(hwnd, lparam):
        if user32.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buf, 256)
            cls = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls, 256)
            rect = ctypes.wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            w, h = rect.right - rect.left, rect.bottom - rect.top
            if w > 40 and h > 30 and ("CapCut" in buf.value or "Qt6" in cls.value):
                found.append((hwnd, buf.value, cls.value, rect.left, rect.top, w, h))
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return found


def target_for_screen_pt(wins, sx, sy):
    hit_top = None
    for hwnd, title, cls, l, t, w, h in wins:
        if l <= sx < l + w and t <= sy < t + h:
            hit_top = hwnd
            break
    if not hit_top and wins:
        hit_top = wins[0][0]
    cur = hit_top
    pt = ctypes.wintypes.POINT(int(sx), int(sy))
    while True:
        cpt = ctypes.wintypes.POINT(pt.x, pt.y)
        user32.ScreenToClient(cur, ctypes.byref(cpt))
        child = user32.ChildWindowFromPointEx(cur, cpt, 0x0003)
        if not child or child == cur:
            return cur, cpt.x, cpt.y
        cur = child


def post_click(wins, sx, sy):
    hwnd, cx, cy = target_for_screen_pt(wins, sx, sy)
    user32.SetForegroundWindow(hwnd)
    user32.SendMessageW(hwnd, WM_ACTIVATE, 1, 0)
    user32.SendMessageW(hwnd, WM_SETFOCUS, 0, 0)
    lp = makelparam(cx, cy)
    user32.PostMessageW(hwnd, WM_MOUSEMOVE, 0, lp)
    time.sleep(0.05)
    user32.PostMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lp)
    time.sleep(0.06)
    user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lp)


def post_drag(wins, x1, y1, x2, y2, steps=25):
    hwnd, cx1, cy1 = target_for_screen_pt(wins, x1, y1)
    cpt2 = ctypes.wintypes.POINT(int(x2), int(y2))
    user32.ScreenToClient(hwnd, ctypes.byref(cpt2))
    cx2, cy2 = cpt2.x, cpt2.y
    user32.SetForegroundWindow(hwnd)
    user32.SendMessageW(hwnd, WM_ACTIVATE, 1, 0)
    user32.PostMessageW(hwnd, WM_MOUSEMOVE, 0, makelparam(cx1, cy1))
    time.sleep(0.05)
    user32.PostMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, makelparam(cx1, cy1))
    time.sleep(0.05)
    for i in range(1, steps + 1):
        mx = int(cx1 + (cx2 - cx1) * i / steps)
        my = int(cy1 + (cy2 - cy1) * i / steps)
        user32.PostMessageW(hwnd, WM_MOUSEMOVE, MK_LBUTTON, makelparam(mx, my))
        time.sleep(0.03)
    user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, makelparam(cx2, cy2))


def post_type(hwnd, text, enter=True):
    user32.SetForegroundWindow(hwnd)
    user32.SendMessageW(hwnd, WM_ACTIVATE, 1, 0)
    user32.SendMessageW(hwnd, WM_SETFOCUS, 0, 0)
    for ch in text:
        user32.PostMessageW(hwnd, WM_CHAR, ord(ch), 1)
        time.sleep(0.03)
    if enter:
        time.sleep(0.1)
        user32.PostMessageW(hwnd, WM_KEYDOWN, 0x0D, 0x001C0001)
        time.sleep(0.05)
        user32.PostMessageW(hwnd, WM_KEYUP, 0x0D, 0xC01C0001)


def grab_composite(wins) -> Image.Image:
    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", ctypes.c_uint32),
            ("biWidth", ctypes.c_int32),
            ("biHeight", ctypes.c_int32),
            ("biPlanes", ctypes.c_uint16),
            ("biBitCount", ctypes.c_uint16),
            ("biCompression", ctypes.c_uint32),
            ("biSizeImage", ctypes.c_uint32),
            ("biXPelsPerMeter", ctypes.c_int32),
            ("biYPelsPerMeter", ctypes.c_int32),
            ("biClrUsed", ctypes.c_uint32),
            ("biClrImportant", ctypes.c_uint32),
        ]

    canvas = Image.new("RGB", (1920, 1080), (15, 15, 20))
    for hwnd, title, cls, l, t, w, h in reversed(wins):
        hwndDC = user32.GetWindowDC(hwnd)
        mfcDC = gdi32.CreateCompatibleDC(hwndDC)
        bmp = gdi32.CreateCompatibleBitmap(hwndDC, w, h)
        old = gdi32.SelectObject(mfcDC, bmp)
        user32.PrintWindow(hwnd, mfcDC, 2)
        bmi = BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth = w
        bmi.biHeight = -h
        bmi.biPlanes = 1
        bmi.biBitCount = 32
        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(mfcDC, bmp, 0, h, buf, ctypes.byref(bmi), 0)
        gdi32.SelectObject(mfcDC, old)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mfcDC)
        user32.ReleaseDC(hwnd, hwndDC)
        im = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB")
        canvas.paste(im, (l, t))
    return canvas


def bump_draft_to_top(draft_folder: Path):
    root_p = Path(r"C:\Users\tmd39\AppData\Local\CapCut\User Data\Projects\com.lveditor.draft\root_meta_info.json")
    d = json.loads(root_p.read_text(encoding="utf-8"))
    max_tm = max((x.get("tm_draft_modified", 0) for x in d.get("all_draft_store", [])), default=int(time.time() * 1_000_000))
    new_tm = max(max_tm + 10_000_000, int(time.time() * 1_000_000))
    for x in d.get("all_draft_store", []):
        if x.get("draft_name") == draft_folder.name:
            x["tm_draft_modified"] = new_tm
    root_p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    meta_p = draft_folder / "draft_meta_info.json"
    if meta_p.exists():
        md = json.loads(meta_p.read_text(encoding="utf-8"))
        md["tm_draft_modified"] = new_tm
        meta_p.write_text(json.dumps(md, ensure_ascii=False), encoding="utf-8")


def run_auto_tts(job: str, edl_name: str, voice: str = "vibrant_baritone", speed: float = 1.1):
    all_lines = lines_of(read_json(JOBS / job / edl_name))
    missing = [s for s in all_lines if not (ASSETS / "voices" / voice / f"{key(s)}.wav").exists()]
    if not missing:
        print(f"[capcut_auto_tts] 모든 문장({len(all_lines)}개)이 이미 {voice} 에 준비되어 있습니다.")
        return

    subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Process CapCut -ErrorAction SilentlyContinue | Stop-Process -Force"], check=False)
    time.sleep(1.0)

    make(job, edl_name, voice)
    man = read_json(JOBS / job / f"capcut_voice_{voice}.json")
    draft_folder = Path(man["draft"])
    bump_draft_to_top(draft_folder)

    env = os.environ.copy()
    env["QSG_RHI_BACKEND"] = "opengl"
    env["QT_OPENGL"] = "software"
    proc = subprocess.Popen([resolve_capcut_exe()], env=env)
    try:
        time.sleep(9.0)
        wins = find_capcut_windows()
        if not wins:
            raise RuntimeError("CapCut 창을 찾지 못했습니다.")
        main_win = max(wins, key=lambda x: x[5] * x[6])[0]
        for w in wins:
            if w[0] != main_win:
                user32.PostMessageW(w[0], WM_CLOSE, 0, 0)
        time.sleep(0.8)
        user32.ShowWindow(main_win, 3)
        time.sleep(1.2)

        # Open first project tile on Home screen
        wins = find_capcut_windows()
        post_click(wins, 300, 750)
        time.sleep(6.5)
        wins = find_capcut_windows()
        main_win = max(wins, key=lambda x: x[5] * x[6])[0]
        user32.ShowWindow(main_win, 3)
        time.sleep(1.5)

        # Measure orange text track X range and marquee-select all segments
        wins = find_capcut_windows()
        im_ed = np.array(grab_composite(wins))
        ys = np.where((im_ed[700:900, 230, 0] > 150) & (im_ed[700:900, 230, 1] < 120))[0] + 700
        ym = int(ys.mean()) if len(ys) else 832
        xs = np.where((im_ed[ym, 150:1860, 0] > 140) & (im_ed[ym, 150:1860, 1] < 120))[0] + 150
        x_right = min(1840, (int(xs.max()) + 60) if len(xs) else 1530)

        post_drag(wins, x_right, ym - 22, 165, ym + 22, steps=25)
        time.sleep(1.0)

        # Click 텍스트에서 음성으로 tab -> search '활기찬 바리톤'
        wins = find_capcut_windows()
        post_click(wins, 1535, 50)
        time.sleep(1.2)
        post_click(wins, 1450, 94)
        time.sleep(0.8)
        main_win = max(wins, key=lambda x: x[5] * x[6])[0]
        post_type(main_win, "활기찬 바리톤", enter=True)
        time.sleep(3.2)

        # Measure cyan '음성 생성' button center & click Vibrant Baritone + 음성 생성
        wins = find_capcut_windows()
        im_srch = np.array(grab_composite(wins))
        mask = (im_srch[550:700, 1800:1915, 0] < 60) & (im_srch[550:700, 1800:1915, 1] > 170) & (im_srch[550:700, 1800:1915, 2] > 170)
        bys, bxs = np.where(mask)
        bx = int(bxs.mean() + 1800) if len(bxs) else 1862
        by = int(bys.mean() + 550) if len(bys) else 670

        post_click(wins, 1385, 202)
        time.sleep(2.2)
        post_click(wins, bx, by)

        # Poll until textReading/*.wav count reaches len(man["lines"])
        tr_dir = draft_folder / "textReading"
        deadline = time.time() + 35.0
        while time.time() < deadline:
            if tr_dir.exists() and len(list(tr_dir.glob("*.wav"))) >= len(man["lines"]):
                time.sleep(1.5)
                break
            time.sleep(1.0)
    finally:
        wins = find_capcut_windows()
        for w in wins:
            user32.PostMessageW(w[0], WM_CLOSE, 0, 0)
        time.sleep(2.0)
        proc.terminate()
        subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Process CapCut -ErrorAction SilentlyContinue | Stop-Process -Force"], check=False)

    harvest(job, voice, fallback_speed=speed)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True)
    ap.add_argument("--edl", required=True)
    ap.add_argument("--voice", default="vibrant_baritone")
    ap.add_argument("--speed", type=float, default=1.1)
    a = ap.parse_args()
    run_auto_tts(a.job, a.edl, voice=a.voice, speed=a.speed)


if __name__ == "__main__":
    main()
