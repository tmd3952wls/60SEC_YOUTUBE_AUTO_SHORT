"""참고 쇼츠에서 '한국어 내레이션(TTS) 구간에 화면을 어둡게 하는지' 재기.

python tools/ref_dim_check.py <out.json> <영상들...>
1) faster-whisper 로 말 구간을 나누고, 구간마다 언어를 판별(ko = 내레이션, en = 원본 대사)
2) 영상 패널(가운데 영역) 평균 밝기를 프레임마다 재서
3) 내레이션↔원본 경계 앞뒤 0.3초 밝기 차이 (같은 장면이 이어질 때 어둡게 했는지가 드러남)와 구간 평균을 비교
"""
import json
import subprocess
import sys

import cv2
import numpy as np
from faster_whisper import WhisperModel

out, vids = sys.argv[1], sys.argv[2:]
model = WhisperModel("small", device="cpu", compute_type="int8")


def pcm(path):
    b = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                       capture_output=True).stdout
    return np.frombuffer(b, np.int16).astype(np.float32) / 32768


def luma(path):
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    ys = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        h = f.shape[0]
        g = cv2.cvtColor(f[int(h * 0.22):int(h * 0.62), :], cv2.COLOR_BGR2GRAY)  # 영상 패널 가운데
        ys.append(float(g.mean()))
    return np.array(ys), fps


res = {}
for v in vids:
    a = pcm(v)
    segs, _ = model.transcribe(a, vad_filter=True, condition_on_previous_text=False)
    segs = list(segs)
    lab = []
    for s in segs:
        clip = a[int(s.start * 16000):int(s.end * 16000)]
        if len(clip) < 16000 * 0.4:
            lab.append(None)
            continue
        lang, p, _ = model.detect_language(clip)
        lab.append(lang if p > 0.6 else None)
    Y, fps = luma(v)
    rows = []
    for s, l in zip(segs, lab):
        i0, i1 = int(s.start * fps), max(int(s.start * fps) + 1, int(s.end * fps))
        rows.append({"a": round(s.start, 2), "b": round(s.end, 2), "lang": l, "luma": round(float(Y[i0:i1].mean()), 1),
                     "text": s.text.strip()[:40]})
    # 경계: ko→en, en→ko 가 0.4초 안에 붙어 있을 때 앞뒤 0.3초 밝기
    steps = []
    for r0, r1 in zip(rows, rows[1:]):
        if r0["lang"] in ("ko", "en") and r1["lang"] in ("ko", "en") and r0["lang"] != r1["lang"] and r1["a"] - r0["b"] < 0.4:
            t = (r0["b"] + r1["a"]) / 2
            pre = Y[max(0, int((t - 0.3) * fps)):int(t * fps)].mean()
            post = Y[int(t * fps):int((t + 0.3) * fps)].mean()
            steps.append({"t": round(t, 2), "kind": f'{r0["lang"]}->{r1["lang"]}', "pre": round(float(pre), 1),
                          "post": round(float(post), 1)})
    ko = [r["luma"] for r in rows if r["lang"] == "ko"]
    en = [r["luma"] for r in rows if r["lang"] == "en"]
    res[v] = {"rows": rows, "steps": steps, "ko_mean": round(float(np.mean(ko)), 1) if ko else None,
              "en_mean": round(float(np.mean(en)), 1) if en else None}
    print(v.split("/")[-1].split("\\")[-1], "ko", res[v]["ko_mean"], "en", res[v]["en_mean"],
          "| 경계", [(s["kind"], s["pre"], s["post"]) for s in steps], flush=True)
json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
