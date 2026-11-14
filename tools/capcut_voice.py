"""CapCut AI 목소리(텍스트 읽기 · 활기찬 바리톤 vibrant_baritone 기본) 내레이션 도구.

CapCut 목소리는 외부 HTTP API 가 없어서 CapCut 안에서 한 번 읽혀 가져옵니다:
  1) make    : 아직 음성이 없는 EDL 내레이션 문장만 텍스트 트랙으로 깔린 CapCut 프로젝트를 생성
  2) (사용자) CapCut 에서 텍스트 전부 선택 → 텍스트 읽기 → '활기찬 바리톤' (1.1배속) 적용 → 저장 후 종료
  3) harvest : 생성된 음성 파일을 문장별 해시(assets/voices/<목소리>/<md5>.wav)로 추출·저장
그 뒤 config.json 의 tts.provider = "capcut" (tts.capcut.voice = "vibrant_baritone") 으로 렌더하면 자동 사용됩니다.

  python tools/capcut_voice.py make --job socks --edl v9_edl.json --voice vibrant_baritone
  python tools/capcut_voice.py harvest --job socks --voice vibrant_baritone [--fallback-speed 1.1]
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

from shorts import capcut as C  # noqa: E402
from shorts.common import ASSETS, JOBS, read_json, write_json  # noqa: E402

SAY = {"ㄹㅇ": "진짜"}


def plain_text(text):
    return re.sub(r"\[(\w+:)?|\]", "", str(text or ""))


def tts_say(text):
    out = []
    for w in text.split():
        w = SAY.get(w, w)
        w = re.sub(r"[ㄱ-ㅎㅏ-ㅣ;@~]+", "", w)
        if w.strip():
            out.append(w)
    return " ".join(out)


def key(text):
    return hashlib.md5(text.strip().encode("utf-8")).hexdigest()[:16]


def lines_of(edl):
    out = []
    for it in edl.get("items") or []:
        if it.get("type") == "narration":
            s = tts_say(plain_text(it.get("text", "")))
            if s and s not in out:
                out.append(s)
    return out


def make(job, edl_name, voice):
    all_lines = lines_of(read_json(JOBS / job / edl_name))
    lines = [s for s in all_lines if not (ASSETS / "voices" / voice / f"{key(s)}.wav").exists()]
    if not lines:
        print(f"완료: 새로 만들 문장 없음 ({voice} 음성 {len(all_lines)}개 모두 이미 준비됨)")
        return
    name, n = f"voice_{job}_{voice}", 1
    while (C.draft_root() / name).exists():
        n += 1
        name = f"voice_{job}_{voice}_{n}"
    folder = C.draft_root() / name
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
        print(f"만듦: {name} (문장 {len(lines)}개) — CapCut 이 켜져 있어 목록 등록은 미룸 (CapCut 재시작 또는 목록 등록 버튼 사용)")
    else:
        print(f"만듦: {name} (문장 {len(lines)}개) —", C.register(folder, meta))
    for s in lines:
        print("  ·", s)
    print(f"완료: CapCut 에서 '{name}' 프로젝트를 열고 텍스트 전체 선택 → 텍스트 읽기 → '활기찬 바리톤' 적용 후 닫아 주세요.")


def harvest(job, voice, fallback_speed=0.0):
    man_path = JOBS / job / f"capcut_voice_{voice}.json"
    if not man_path.is_file():
        raise FileNotFoundError(f"먼저 '1단계: CapCut 보내기(make)' 를 실행해 주세요 ({man_path.name} 없음)")
    man = read_json(man_path)
    folder = Path(man["draft"])
    if not (folder / "draft_content.json").is_file():
        raise FileNotFoundError(f"CapCut 프로젝트 폴더를 찾을 수 없습니다: {folder}")
    d = json.loads((folder / "draft_content.json").read_text(encoding="utf-8"))
    M = d["materials"]
    audios = {a["id"]: a for a in M.get("audios", [])}
    texts = {t["id"]: t for t in M.get("texts", [])}
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
            print("  ✗ 음성 없음 (CapCut 에서 텍스트 읽기를 아직 적용하지 않음):", text)
            continue
        src = Path(re.sub(r"^##_draftpath_placeholder_[^#]+_##", folder.as_posix(), audios[aid]["path"]))
        if not src.exists():
            print("  ✗ 파일 없음:", src)
            continue
        seg = next((s for s in asegs if s["material_id"] == aid), None)
        speed = float(seg.get("speed") or 1.0) if seg else 1.0
        if abs(speed - 1.0) <= 1e-3 and fallback_speed and abs(fallback_speed - 1.0) > 1e-3:
            speed = float(fallback_speed)
        dst = out_dir / f"{key(text)}.wav"
        af = ["-af", f"atempo={speed}"] if abs(speed - 1) > 1e-3 else []
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), *af, "-ar", "48000", "-ac", "2", str(dst)],
                       check=True)
        print(f"  ✓ x{speed:.2f} {text}  ← {audios[aid].get('tone_type') or voice}")
        got += 1
    print(f"완료: 가져옴 {got}/{len(man['lines'])}문장 → {out_dir.name}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["make", "harvest"])
    ap.add_argument("--job", required=True)
    ap.add_argument("--edl", default="")
    ap.add_argument("--voice", default="vibrant_baritone")
    ap.add_argument("--fallback-speed", type=float, default=0.0,
                    help="CapCut 프로젝트 안에서 배속이 1.0 인 경우 자동 적용할 기본 배속 (예: 1.1)")
    a = ap.parse_args()
    if a.cmd == "make":
        make(a.job, a.edl, a.voice)
    else:
        harvest(a.job, a.voice, fallback_speed=a.fallback_speed)


if __name__ == "__main__":
    main()
