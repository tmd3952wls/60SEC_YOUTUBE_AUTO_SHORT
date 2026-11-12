"""CapCut AI 목소리(텍스트 읽기)로 내레이션 만들기 (2026-11-12).

CapCut 목소리는 외부 API 가 없어서, CapCut 안에서 사람이 버튼만 누르게 함:
  1) make    : EDL 내레이션 문장만 텍스트로 깔린 CapCut 프로젝트를 만듦
  2) (사용자) CapCut 에서 텍스트 전부 선택 → 텍스트 읽기 → 목소리 고르기 → 적용 → 저장 후 종료
  3) harvest : 그 프로젝트에서 생성된 음성 파일을 문장별로 assets/voices/<목소리>/<md5>.wav 로 가져옴
그 뒤 config tts.provider = "capcut" (tts.capcut.voice = 목소리 이름) 으로 렌더하면 그 음성을 씀.

  python tools/capcut_voice.py make --job socks --edl v9_edl.json --voice vibrant_baritone
  python tools/capcut_voice.py harvest --job socks --voice vibrant_baritone
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from shorts import capcut as C  # noqa: E402
from shorts.common import ASSETS, JOBS, read_json, write_json  # noqa: E402
from shorts.edl import plain, tts_say  # noqa: E402


def key(text):
    return hashlib.md5(text.strip().encode("utf-8")).hexdigest()[:16]


def lines_of(edl):
    out = []
    for it in edl["items"]:
        if it.get("type") == "narration":
            s = tts_say(plain(it["text"]))
            if s and s not in out:
                out.append(s)
    return out


def make(job, edl_name, voice):
    lines = lines_of(read_json(JOBS / job / edl_name))
    name = f"voice_{job}_{voice}"
    folder = C.draft_root() / name
    if folder.exists():
        sys.exit(f"이미 있음: {folder} (지우거나 다른 이름으로)")
    t, spans = 0.0, []
    for s in lines:
        dur = max(2.0, len(s.replace(" ", "")) * 0.22 + 1.0)
        spans.append((s, t, dur))
        t += dur + 0.5
    d = C.Draft(t, name, folder)
    tr = d.track("text", "내레이션 문장")
    for s, a, dur in spans:
        d.add_text(tr, [(s, "white")], a, dur, 8.0, 960, shadow=False)
    meta = d.write()
    write_json(JOBS / job / f"capcut_voice_{voice}.json", {"draft": folder.as_posix(), "voice": voice, "lines": lines})
    if C.capcut_running():
        pend = read_json(C.PENDING) if C.PENDING.exists() else []
        write_json(C.PENDING, pend + [folder.as_posix()])
        print(f"만듦: {name} (문장 {len(lines)}개) — CapCut 이 켜져 있어 목록 등록은 미룸")
    else:
        print(f"만듦: {name} (문장 {len(lines)}개) —", C.register(folder, meta))
    for s in lines:
        print("  ·", s)


def harvest(job, voice):
    man = read_json(JOBS / job / f"capcut_voice_{voice}.json")
    folder = Path(man["draft"])
    d = json.loads((folder / "draft_content.json").read_text(encoding="utf-8"))
    M = d["materials"]
    audios = {a["id"]: a for a in M.get("audios", [])}
    texts = {t["id"]: t for t in M.get("texts", [])}
    # 텍스트 → 음성: text_to_audio_ids 가 있으면 그걸, 없으면 시간이 겹치는 음성 조각
    segs = [(s, tr["type"]) for tr in d["tracks"] for s in tr["segments"]]
    tsegs = [s for s, k in segs if k == "text" and s["material_id"] in texts]
    asegs = [s for s, k in segs if k == "audio" and s["material_id"] in audios]
    out_dir = ASSETS / "voices" / voice
    out_dir.mkdir(parents=True, exist_ok=True)
    got = 0
    for ts in tsegs:
        tm = texts[ts["material_id"]]
        text = json.loads(tm["content"])["text"].strip()
        aid = next((i for i in tm.get("text_to_audio_ids") or [] if i in audios), None)
        aid = aid or next((k for k, a in audios.items() if a.get("text_id") == tm["id"]), None)
        if not aid:
            a0 = ts["target_timerange"]["start"]
            best = min(asegs, key=lambda s: abs(s["target_timerange"]["start"] - a0), default=None)
            if best and abs(best["target_timerange"]["start"] - a0) < 300_000:
                aid = best["material_id"]
        if not aid:
            print("  ✗ 음성 없음:", text)
            continue
        import re
        src = Path(re.sub(r"^##_draftpath_placeholder_[^#]+_##", folder.as_posix(), audios[aid]["path"]))
        if not src.exists():
            print("  ✗ 파일 없음:", src)
            continue
        # 사용자가 CapCut 에서 준 배속 (예: 1.1) → 파일에 적용 (CapCut 은 원본 wav + 조각 speed 로 저장)
        seg = next((s for s in asegs if s["material_id"] == aid), None)
        speed = float(seg.get("speed") or 1.0) if seg else 1.0
        dst = out_dir / f"{key(text)}.wav"
        af = ["-af", f"atempo={speed}"] if abs(speed - 1) > 1e-3 else []
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), *af, "-ar", "48000", "-ac", "2", str(dst)],
                       check=True)
        print(f"  ✓ x{speed} {text}  ← {audios[aid].get('tone_type', '')}")
        got += 1
    print(f"가져옴 {got}/{len(man['lines'])} → {out_dir}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["make", "harvest"])
    ap.add_argument("--job", required=True)
    ap.add_argument("--edl", default="")
    ap.add_argument("--voice", required=True)
    a = ap.parse_args()
    make(a.job, a.edl, a.voice) if a.cmd == "make" else harvest(a.job, a.voice)


if __name__ == "__main__":
    main()
