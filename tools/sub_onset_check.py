"""자막 등장 시각 vs 실제 목소리 시작 (소리 에너지로 직접 측정, 2026-11-10).

Whisper 재받아쓰기는 단어 매칭이 틀려서 ±0.3초씩 엉뚱한 값이 나옴 → 목소리만 든 body 소리에서
'조용하다가 소리가 나기 시작하는 순간'을 찾아 각 자막과 비교한다.

python tools/sub_onset_check.py jobs/<작업>
  - edl_tmp/body.mp4 (목소리·원본 대사만, 효과음 없음) + edl_tmp/export.json 의 자막 시각 사용
  - 차이 = 목소리 시작 - 자막 등장. +면 자막이 먼저(좋음, 0~+120ms 권장), -면 자막이 늦음
  - 자막 직전에 쉼이 없으면(말이 이어짐) '이어짐' 으로 표시 — 에너지로는 판단 불가
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np


def env_db(path, hop=0.01):
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    y = np.frombuffer(pcm, np.int16).astype(np.float64) / 32768
    h = int(16000 * hop)
    n = len(y) // h
    r = np.sqrt((y[:n * h].reshape(n, h) ** 2).mean(axis=1) + 1e-12)
    return 20 * np.log10(r)


def onsets(e, min_quiet=0.08):
    """조용(바닥+10dB 미만) min_quiet초 이상 → 소리 시작 프레임들 (초)."""
    floor = np.percentile(e, 10)
    loud = e > max(floor + 10, np.percentile(e, 95) - 38)
    out, q = [], 0
    for i, v in enumerate(loud):
        if not v:
            q += 1
        else:
            if q >= int(min_quiet * 100):
                out.append(i / 100)
            q = 0
    return np.array(out)


def main():
    job = Path(sys.argv[1])
    exp = json.load(open(job / "edl_tmp" / "export.json", encoding="utf-8"))
    e = env_db(job / "edl_tmp" / "body.mp4")
    ons = onsets(e)
    rows, bad = [], 0
    t0s = {it["n"]: it["t0"] for it in exp["items"]}
    for s in exp["subs"]:
        a = s["a"]
        lo = max(a - 0.5, t0s.get(s.get("item"), 0) + 0.02)  # 같은 항목 안에서만 (앞 항목 말 끝을 잡지 않게)
        text = "".join(t for t, _ in s["spans"]).replace("\n", " ").strip() or s.get("note", "")
        near = ons[(ons > lo) & (ons < a + 0.4)]
        if not len(near):
            rows.append(f"{a:7.2f}s |   이어짐  | {text}")
            continue
        o = near[np.argmin(np.abs(near - a))]
        d = (o - a) * 1000
        flag = "  ← 자막 늦음" if d < -40 else ("  ← 자막 너무 이름" if d > 200 else "")
        bad += bool(flag)
        rows.append(f"{a:7.2f}s | {d:+6.0f}ms | {text}{flag}")
    print("자막 등장 | 목소리-자막 | 자막")
    print("\n".join(rows))
    print(f"문제 {bad}개 (자막 늦음 = 목소리가 자막보다 40ms 넘게 먼저)")


if __name__ == "__main__":
    main()
