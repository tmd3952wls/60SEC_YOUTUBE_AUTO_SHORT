"""참고 영상에 '똑같은 효과음 파일'이 쓰였는지 찾기 (스펙트로그램 지문 대조).

python tools/sfx_fingerprint.py <out.json> --refs <오디오 파일들...> --libs <라이브러리 폴더들...>

라이브러리 소리마다 앞부분(최대 1.5초) 로그-멜 스펙트로그램을 '도장'으로 삼아 참고 오디오 위를 밀며
피어슨 상관을 계산. 같은 파일이 쓰였으면 배경음악이 깔려도 상관이 높게 튐(우연은 보통 0.3 안팎).
"""
import argparse
import glob
import json
import os

import librosa
import numpy as np
from scipy.signal import fftconvolve

SR, HOP, NM = 22050, 256, 64
AUD = (".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac")


def load(path, duration=None):
    import subprocess
    cmd = ["ffmpeg", "-v", "error", "-i", path] + (["-t", str(duration)] if duration else []) +           ["-vn", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"]
    return np.frombuffer(subprocess.run(cmd, capture_output=True).stdout, np.float32)


def logmel(y):
    m = librosa.feature.melspectrogram(y=y, sr=SR, n_fft=1024, hop_length=HOP, n_mels=NM, fmin=60, fmax=10000)
    L = librosa.power_to_db(m, ref=np.max, top_db=80).astype(np.float32)
    # 소리가 '생겨나는' 순간(밴드별 증가량)만 남김 → 전체 음색 기울기·깔린 배경음악의 지속음은 빠짐
    return np.maximum(np.diff(L, axis=1, prepend=L[:, :1]), 0.0)


def template(path):
    y = load(path, 6.0)
    if len(y) < SR * 0.08:
        return None
    yt, idx = librosa.effects.trim(y, top_db=35)
    y = y[idx[0]:idx[0] + int(1.5 * SR)]
    if len(y) < SR * 0.08:
        return None
    T = logmel(y)
    T = T - T.mean()
    n = np.linalg.norm(T)
    return (T / n) if n > 1e-6 else None


def scan(X, T):
    """X (NM, n) 참고, T (NM, m) 정규화된 도장 → 위치별 피어슨 상관 (n-m+1)"""
    m = T.shape[1]
    if X.shape[1] < m:
        return np.zeros(0)
    num = sum(fftconvolve(X[b], T[b][::-1], mode="valid") for b in range(NM))
    c1 = np.concatenate([[0], np.cumsum(X.sum(0))])
    c2 = np.concatenate([[0], np.cumsum((X * X).sum(0))])
    s1, s2 = c1[m:] - c1[:-m], c2[m:] - c2[:-m]
    N = NM * m
    den = np.sqrt(np.maximum(s2 - s1 * s1 / N, N * 0.5))  # 무음 구간에서 0으로 나누기 방지
    return num / den


ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--refs", nargs="+", required=True)
ap.add_argument("--libs", nargs="+", required=True)
ap.add_argument("--thr", type=float, default=0.55)
a = ap.parse_args()

lib = []
for d in a.libs:
    for p in sorted(glob.glob(os.path.join(d, "**", "*"), recursive=True)):
        if os.path.splitext(p)[1].lower() in AUD:
            try:
                T = template(p)
            except Exception:
                T = None
            if T is not None:
                lib.append((p, T))
print(f"도장 {len(lib)}개")
res = {"hits": [], "best": {}}
for r in a.refs:
    y = load(r)
    X = logmel(y)
    name = os.path.basename(os.path.dirname(r)) if os.path.basename(r).startswith("no_vocals") else os.path.basename(r)
    for p, T in lib:
        c = scan(X, T)
        if not len(c):
            continue
        k = int(np.argmax(c))
        res["best"].setdefault(p, []).append([name, round(float(c[k]), 3), round(k * HOP / SR, 2)])
        # 임계값 넘는 봉우리 (0.3초 안에서 하나)
        above = np.where(c >= a.thr)[0]
        last = -1e9
        for i in above:
            if i - last < 0.3 * SR / HOP:
                continue
            j = i + int(np.argmax(c[i:i + int(0.3 * SR / HOP)]))
            res["hits"].append({"ref": name, "t": round(j * HOP / SR, 2), "corr": round(float(c[j]), 3), "sound": p})
            last = j
    print(name, "done", flush=True)
json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
from collections import Counter
cnt = Counter(h["sound"] for h in res["hits"])
print(f"임계값 {a.thr} 넘은 지점 {len(res['hits'])}개")
for s, n in cnt.most_common(40):
    refs = sorted({h["ref"] for h in res["hits"] if h["sound"] == s})
    mx = max(h["corr"] for h in res["hits"] if h["sound"] == s)
    print(f"{n:3d}회 최고 {mx:.2f} 영상 {len(refs)}개  {os.path.basename(s)}")
