"""효과음 믹스 — opus-sound-layer (실제 녹음 CC0 1,139개) 로.

2026-11-08 사용자 결정: 예전 효과음 폴더(sfxlib) 소리가 어색해서, full_v6 방식(한 계열의 실제 녹음 +
목소리 대비 소리별 음량 + 공유 공간 울림 + -14 LUFS 마스터)을 기본으로.

렌더러(edl.py)가 정한 효과음 '시점·종류'는 그대로 쓰고, 소리만 아래 FAMILY 에서 차례로 고른다.
  카테고리 이름: whoosh, pop, ding, question, impact, success, surprise, fail, tension, caption, camera
  "whoosh/fs-30240-swoop1-flac-1" 처럼 라이브러리 id 를 직접 적으면 그 소리를 그대로 씀.
"""
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np

from .common import ROOT

OPUS = ROOT / "ext" / "opus-sound-layer"
KIT = OPUS / "audio" / "kit"
SR = 48000

# 한 영상 = 한 소리 계열 (공기 휙 · 천 스치는 소리 · 물방울 팝 · 나무 톡 · 종). 같은 종류는 차례로 돌려 반복을 피함.
FAMILY = {
    # 순서 = full_v6 (사용자가 듣고 좋다고 한 판) 에서 쓴 차례 그대로
    "whoosh": ["whoosh/fs-30240-swoop1-flac-1", "swish/fs-14175-27-wav-1", "whoosh/fs-449992-whoosh-short-low-wav-1",
               "whoosh/fs-30241-swoop2g-flac-1", "swish/fs-388003-double-swish-1",
               "whoosh/fs-449988-whoosh-med-high-1", "swish/kenney-rpg-cloth1",
               "whoosh/fs-449989-whoosh-long-mid-wav-1", "whoosh/fs-60026-swosh-swoosh-whoosh-air-soun-1"],
    "pop": ["pop/fs-269583-bubble-1", "pop/fs-174695-sci-fi-bubble-pop-3", "pop/fs-507006-soap-bubbles-pop-1",
            "pop/fs-174695-sci-fi-bubble-pop-1", "pop/fs-253956-bubble-pop-1", "pop/fs-644759-soap-bubble-pop-mouth-perc-w-1"],
    "ding": ["chime/fs-571513-soft-notifications-bell-ding-2", "chime/fs-255101-jingle2-3",
             "chime/fs-570243-point-in-space-ogg-1", "chime/fs-127149-ding-wav-1", "chime/fs-404104-glass-ding-3"],
    "question": ["tap/fs-369710-wood-knock", "tap/kenney-impact-impact-wood-light-001",
                 "tap/kenney-impact-impact-wood-light-003", "tap/kenney-impact-impact-wood-light-004"],
    "impact": ["hit/fs-113747-kl-ex1bb-wav-2+boom/fs-636624-deep-hit-2"],
    "success": ["chime/fs-582655-long-rising-tones-16-wav-2", "chime/fs-159011-ding2-wav-1"],
    "surprise": ["shimmer/fs-449645-transition-action-jump-pitch-1", "reverse/fs-148930-cymbal-hits-reversed-wav-1"],
    "fail": ["thump/fs-389665-thump-close-wav-2", "thump/fs-405537-thud-2-wav-1"],
    "tension": ["tick/fs-403001-clock-tick-tik-tak-2", "tick/fs-130388-clock-ticking-1"],
    "caption": ["key/fs-194795-vintage-keyboard-1-1", "key/fs-194797-vintage-keyboard-3-1"],
    "camera": ["click/kenney-ui-audio-switch16", "click/fs-399443-mouse-clicks"],
}
HERO = {"impact"}  # 한 영상의 큰 한 방: 직전 정적 + 짧게 차오르는 소리
BUILD = "riser/fs-531729-energy-riser-3-1"


def available():
    return (KIT / "catalog.json").exists() and shutil.which("uv") is not None


def _sound(cat, used):
    if "/" in cat:
        typ, rest = cat.split("/", 1)
        if (KIT / typ / f"{rest}.wav").exists():
            return cat
        cat = typ  # 예전 효과음 폴더의 고정 이름("pop/카툰 팝") → 같은 종류에서 고름
    opts = FAMILY.get(cat) or FAMILY["pop"]
    k = used.get(cat, 0)
    used[cat] = k + 1
    return opts[k % len(opts)]


def _read(path):
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True).stdout
    return np.frombuffer(pcm, np.float32)


def _peak_offset(x):  # mix.py 와 같은 계산 (2ms 포락선 최대)
    n = max(1, int(0.002 * SR))
    env = np.sqrt(np.convolve(x * x, np.ones(n) / n, mode="same"))
    return int(np.argmax(env))


def _cues(sfx_ev):
    used, cues = {}, []
    for k, (t, cat) in enumerate(sorted(sfx_ev, key=lambda e: e[0])):
        base = cat.split("/")[0]
        c = {"id": f"{k:02d}-{base}", "t": round(max(0.0, t), 4), "sound": _sound(cat, used), "align": "peak",
             "weight": "hero" if base in HERO else "support", "_cat": base}
        cues.append(c)
        if base in HERO:
            c.update({"stop_before": True, "build": True})
            # 같은 시점의 보조음은 히어로 '뒤'에 둬야 mix.py 가 보조음을 0.6배로 줄여 히어로 몸통을 가리지 않음
            cues.append({"id": f"{k:02d}-build", "t": c["t"], "sound": BUILD, "align": "peak", "weight": "support"})
    return cues


def _mix(work, total, cues):
    sheet = {"fps": 30, "duration_s": round(total, 3), "energy": "punchy", "kit": KIT.as_posix(),
             "room": {"decay_s": 0.5, "wet_db": -18}, "voice": [{"file": "vo.wav", "start_s": 0}], "duck_db": 0,
             "silence_ok": [[max(0.0, total - 0.8), total]],
             "cues": [{k: v for k, v in c.items() if not k.startswith("_")} for c in cues]}
    (work / "cues.json").write_text(json.dumps(sheet, ensure_ascii=False, indent=1), encoding="utf-8")
    r = subprocess.run(["uv", "run", "--project", str(OPUS), str(OPUS / "scripts" / "mix.py"), "cues.json"],
                       cwd=work, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise RuntimeError("opus mix.py 실패: " + r.stderr[-1500:])
    return json.loads((work / "audio" / "mix-report.json").read_text(encoding="utf-8"))


def qa(video, work):
    """opus qa.py — FAIL/warn 줄만 돌려줌."""
    r = subprocess.run(["uv", "run", "--project", str(OPUS), str(OPUS / "scripts" / "qa.py"), str(video)],
                       cwd=work, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (r.stdout or "") + "\n" + (r.stderr or "")
    return [l.strip() for l in out.splitlines() if l.startswith(("FAIL", "warn"))]


def render(job, body, video, out, sfx_ev, total, work, rounds=2):
    """목소리만 든 body + 효과음 시점 → 믹스 → video 그림에 붙여 out 으로 → qa.py.
    qa 에서 '안 들림'이 나온 효과음은 같은 종류의 다음 후보로 바꿔 최대 rounds 번 다시 믹스 (PROMPT.md 규칙).
    돌려줌: (CapCut 용 효과음 목록, 목소리 음량 dB, 로그 줄들)"""
    work = Path(work)
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(body), "-vn", "-ac", "2", "-ar", str(SR),
                    "-c:a", "pcm_s24le", str(work / "vo.wav")], check=True)
    cues = _cues(sfx_ev)
    log, swap = [], {}
    for rnd in range(rounds + 1):
        rep = _mix(work, total, cues)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-i", str(work / "audio" / "mix.wav"),
                        "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                        "-movflags", "+faststart", "-t", f"{total:.3f}", str(out)], check=True)
        bad = qa(out, work)
        fails = [l for l in bad if l.startswith("FAIL")]
        log.append(f"  opus qa {rnd + 1}회차: " + ("; ".join(bad) if bad else "모두 통과"))
        changed = False
        for l in fails:
            parts = l.split()
            if len(parts) >= 3 and parts[1] == "audible":
                c = next((c for c in cues if c["id"] == parts[2]), None)
                opts = FAMILY.get(c.get("_cat", "")) if c else None
                if opts and len(opts) > 1:
                    swap[c["id"]] = swap.get(c["id"], 0) + 1
                    taken = {x["sound"] for x in cues}
                    k0 = opts.index(c["sound"]) if c["sound"] in opts else -1
                    order = [(k0 + j) % len(opts) for j in range(1, len(opts) + 1)]
                    i = next((j for j in order if opts[j] not in taken), order[0])  # 영상 안에서 안 쓴 소리 먼저
                    log.append(f"    → {c['id']}: {c['sound']} 대신 {opts[i]}")
                    c["sound"] = opts[i]
                    changed = True
        if not changed or rnd == rounds:
            break
    M = rep["master_gain_db"]
    # 목소리 최종 음량 = 원래 목소리 대비 stems/voice.wav (마스터 적용) 비율
    v0, v1 = _read(work / "vo.wav"), _read(work / "audio" / "stems" / "voice.wav")
    n = min(len(v0), len(v1))
    voice_db = float(20 * np.log10(np.sqrt((v1[:n] ** 2).mean()) / (np.sqrt((v0[:n] ** 2).mean()) + 1e-12)))
    head = [f"효과음(opus): {rep['master_lufs']} LUFS, TP {rep['master_true_peak_db']} dBTP, 이벤트 {len(rep['events'])}개"]
    capcut = []
    for ev in rep["events"]:
        head.append(f"  {ev['peak_s']:.2f}s {ev['sound']} ({ev['gain_db']:+.1f}dB, {ev['limited_by']})")
        for i, f in enumerate(ev["files"]):
            x = _read(f)
            start = ev["peak_s"] - _peak_offset(x) / SR
            total_db = ev["gain_db"] + (0 if i == 0 else -4) + M  # mix.py: 둘째 층부터 -4dB
            capcut.append({"t": max(0.0, start), "cat": ev["id"], "name": Path(f).stem, "file": str(Path(f)),
                           "lead": max(0.0, -start), "gain_db": total_db - voice_db, "max_dur": None})
    return capcut, voice_db, head + log
