"""효과음 색인 검수: 실제 소리가 카테고리와 맞는지(CLAP 소리 분류) + 앞부분 무음 길이.

듣지 않고 확인하기 위한 객관 지표. 결과 → assets/sfx_clap.json
  {파일경로: {"top": 라벨, "p": 확률, "ok": 카테고리와 일치?, "lead": 앞 무음(초)}}
shorts/sfxlib.pick 은 ok=False 인 파일을 고르지 않고, 렌더러는 lead 만큼 앞을 잘라 소리가 사건과 같은 프레임에 나게 한다.
실행: .venv-whisperx/Scripts/python.exe -I tools/sfx_clap_check.py
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding="utf-8")

LABELS = {
    "whoosh": "a whoosh swoosh transition sound", "ding": "a coin ding chime", "boing": "a cartoon boing spring sound",
    "bubble": "a water drop bubble pop", "levelup": "a video game level up jingle", "voice": "a person speaking",
    "laugh": "people laughing", "music": "background music", "impact": "a heavy impact hit",
    "camera": "a camera shutter", "bell": "a notification bell", "clink": "a glass clink", "buzzer": "an error buzzer",
    "drumroll": "a drum roll", "typewriter": "a typewriter key click", "snap": "a finger snap",
    "fanfare": "a short fanfare tada", "register": "a cash register",
}
# 카테고리별로 허용하는 소리 (CLAP 1위 라벨 기준)
ACCEPT = {
    "whoosh": {"whoosh"}, "pop": {"bubble", "boing", "snap"}, "ding": {"ding", "bell", "clink", "register"},
    "impact": {"impact", "drumroll"}, "surprise": {"boing", "impact", "whoosh"}, "question": {"boing"},
    "success": {"levelup", "fanfare", "ding", "bell"}, "fail": {"buzzer", "boing"}, "tension": {"drumroll", "impact"},
    "caption": {"typewriter", "snap", "bubble"}, "camera": {"camera"},
}


def load(p, sr=48000):
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", p, "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"],
                         capture_output=True).stdout
    return np.frombuffer(pcm, np.int16).astype(np.float32) / 32768


def main():
    import torch
    from transformers import ClapModel, ClapProcessor
    m = ClapModel.from_pretrained("laion/clap-htsat-unfused")
    pr = ClapProcessor.from_pretrained("laion/clap-htsat-unfused")
    keys = list(LABELS)
    with torch.no_grad():
        te = m.get_text_features(**pr(text=[LABELS[k] for k in keys], return_tensors="pt", padding=True))
    te = te / te.norm(dim=-1, keepdim=True)
    lib = json.loads((ROOT / "assets/sfx_library.json").read_text(encoding="utf-8"))
    out = {}
    for cat, items in lib.items():
        for it in items:
            x = load(it["file"])
            env = 20 * np.log10(np.abs(x) + 1e-6)
            lead = float(np.argmax(env > env.max() - 40)) / 48000  # 진짜 무음만 (피크-40dB 를 처음 넘는 지점, 휙 소리의 커지는 부분은 남김)
            with torch.no_grad():
                ae = m.get_audio_features(**pr(audios=[x[:48000 * 10]], sampling_rate=48000, return_tensors="pt"))
            ae = ae / ae.norm(dim=-1, keepdim=True)
            p = (100 * ae @ te.T).softmax(-1)[0].numpy()
            top = keys[int(p.argmax())]
            ok = top in ACCEPT.get(cat, set())
            out[it["file"]] = {"cat": cat, "name": it["name"], "top": top, "p": round(float(p.max()), 2),
                               "ok": ok, "lead": round(lead, 3)}
            print(f"{'✓' if ok else '✗'} {cat:8s} {it['name']:18s} → {top:9s} {p.max() * 100:3.0f}%  앞무음 {lead * 1000:4.0f}ms")
    (ROOT / "assets/sfx_clap.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    bad = [v for v in out.values() if not v["ok"]]
    print(f"\n{len(out)}개 중 카테고리 불일치 {len(bad)}개, 앞무음 50ms 넘는 파일 {sum(v['lead'] > 0.05 for v in out.values())}개")


if __name__ == "__main__":
    main()
