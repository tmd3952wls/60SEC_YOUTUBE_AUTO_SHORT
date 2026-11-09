"""참고 영상의 효과음을 찾아 내 효과음 라이브러리에서 가장 비슷한 소리를 고른다.

1) Demucs 로 분리한 참고 영상 배경 트랙(no_vocals.wav)에서 배경음보다 9dB 이상 튀는 순간 = 효과음 후보
2) 후보 구간(시작~0.8초)과 라이브러리 전체(600개)를 CLAP 오디오 임베딩으로 비교 → 가장 비슷한 파일 3개
3) 컷·내레이션 시작·원본 대사 시작과의 관계도 함께 기록
실행: .venv-whisperx/Scripts/python.exe -I tools/ref_sfx_match.py <no_vocals.wav> <ref.mp4> <ref.tr.json> <out.json>
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding="utf-8")
SR = 48000


def load(p, sr=SR):
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"],
                         capture_output=True).stdout
    return np.frombuffer(pcm, np.int16).astype(np.float32) / 32768


def env_db(x, hop):
    n = len(x) // hop
    return 20 * np.log10(np.sqrt((x[:n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-6)


def cuts_of(mp4):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(mp4), "-an", "-vf",
                        "crop=720:700:0:290,scale=240:-1,select='gt(scene,0.25)',showinfo", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    return [float(v) for v in re.findall(r"pts_time:([\d.]+)", r)]


def main():
    nv, mp4, trp, outp = sys.argv[1:5]
    import torch
    from transformers import ClapModel, ClapProcessor
    m = ClapModel.from_pretrained("laion/clap-htsat-unfused")
    pr = ClapProcessor.from_pretrained("laion/clap-htsat-unfused")

    def emb(xs):
        with torch.no_grad():
            e = m.get_audio_features(**pr(audios=xs, sampling_rate=SR, return_tensors="pt"))
        return (e / e.norm(dim=-1, keepdim=True)).numpy()

    # 라이브러리 임베딩 (캐시)
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    lib = Path(cfg["sfx_library"]["dir"])
    cache = ROOT / "assets/sfx_lib_clap.npz"
    files = sorted([str(f) for f in lib.glob("*.mp3")] + [str(f) for f in lib.glob("*.wav")])
    if cache.exists() and list(np.load(cache, allow_pickle=True)["files"]) == files:
        E = np.load(cache, allow_pickle=True)["E"]
    else:
        E = np.concatenate([emb([load(f)[:SR * 3]]) for f in files])
        np.savez(cache, files=np.array(files, dtype=object), E=E)
    # 참고 영상 효과음 후보
    x = load(nv)
    eo = env_db(x, SR // 100)
    bg = np.array([np.median(eo[max(0, i - 60):i + 1]) for i in range(len(eo))])
    ev, i = [], 0
    while i < len(eo):
        if eo[i] - bg[i] > 9 and eo[i] > -40:
            j = i
            while j < len(eo) and eo[j] - bg[i] > 3:
                j += 1
            ev.append((i / 100, (j - i) / 100))
            i = j + 20
        else:
            i += 1
    cuts = cuts_of(mp4)
    tr = json.loads(Path(trp).read_text(encoding="utf-8"))
    near = lambda t, L, w=0.15: min(L, key=lambda c: abs(c - t)) if L and min(abs(c - t) for c in L) <= w else None
    out = []
    for t, d in ev:
        seg = x[int(max(0, t - 0.02) * SR):int((t + max(0.4, min(d, 1.0))) * SR)]
        sim = (emb([seg]) @ E.T)[0]
        top = np.argsort(-sim)[:3]
        sub = next((r for r in tr if r["s"] - 0.1 <= t < r["e"]), None)
        row = {"t": round(t, 2), "dur": round(d, 2),
               "cut": near(t, cuts), "ko_start": near(t, [r["s"] for r in tr if r["ko"]], 0.25),
               "en_start": near(t, [r["s"] for r in tr if not r["ko"]], 0.25),
               "line": sub["t"] if sub else "",
               "match": [(Path(files[k]).stem, round(float(sim[k]), 2)) for k in top]}
        out.append(row)
        rel = "컷" if row["cut"] is not None else ""
        rel += " 내레이션시작" if row["ko_start"] is not None else ""
        rel += " 원본대사시작" if row["en_start"] is not None else ""
        print(f"{t:5.2f}s ({d:.2f}s) [{rel.strip() or '-'}] '{row['line'][:20]}' → "
              + ", ".join(f"{n}({s})" for n, s in row["match"]))
    Path(outp).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n효과음 후보 {len(out)}개 / {len(x) / SR:.0f}초, 서로 다른 1순위 소리 {len({r['match'][0][0] for r in out})}개")


if __name__ == "__main__":
    main()
