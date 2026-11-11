"""컷 길이 + 대사 사이 무음 검사 (2026-11-11, 사용자: "말을 짧게 하면 컷이 순식간에 전환되는 건 옳지 않아,
대본과 대본 사이 무음 구간은 길면 안 돼").

python tools/gap_check.py jobs/<작업> [로그파일 이름=sample_log.txt]
  - 샷 길이 1.0초 미만 → '짧은 컷'
  - 목소리(edl_tmp/body.mp4, 효과음·BGM 없음)에서 0.35초 넘게 조용한 곳 → '무음'
    (영상 맨 끝 고정댓글 안내 뒤는 제외)
"""
import json
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sub_onset_check import env_db  # noqa: E402

MIN_SHOT, MAX_GAP = 1.0, 0.35


def main():
    job = Path(sys.argv[1])
    log = (job / (sys.argv[2] if len(sys.argv) > 2 else "sample_log.txt")).read_text(encoding="utf-8")
    exp = json.load(open(job / "edl_tmp" / "export.json", encoding="utf-8"))
    bad = 0
    shots = [(m.group(1), float(m.group(2)), float(m.group(3)), m.group(4))
             for m in re.finditer(r"(item\d+) shot\d: src [\d.]+~[\d.]+ → out ([\d.]+)~([\d.]+)\s+\((.*)\)", log)]
    for it, a, b, why in shots:
        if b - a < MIN_SHOT:
            print(f"짧은 컷  {a:6.2f}~{b:6.2f}s ({b - a:.2f}초) {it} {why}")
            bad += 1
    e = env_db(job / "edl_tmp" / "body.mp4")
    quiet = e < max(np.percentile(e, 10) + 10, np.percentile(e, 95) - 38)
    end = exp["items"][-1]["t0"]  # 마지막 항목 안(끝맺음)은 제외
    i = 0
    while i < len(quiet):
        if quiet[i]:
            j = i
            while j < len(quiet) and quiet[j]:
                j += 1
            a, b = i / 100, j / 100
            if b - a > MAX_GAP and a < end:
                its = [x["n"] for x in exp["items"] if x["t0"] <= a + 0.01]
                print(f"무음    {a:6.2f}~{b:6.2f}s ({b - a:.2f}초) item{its[-1] if its else '?'}")
                bad += 1
            i = j
        else:
            i += 1
    print(f"문제 {bad}개 (짧은 컷 < {MIN_SHOT}초, 무음 > {MAX_GAP}초)")


if __name__ == "__main__":
    main()
