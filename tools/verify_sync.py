"""내레이션 자막 싱크 검증 (정렬에 쓰지 않은 별도 모델로 측정).

  python tools/verify_sync.py jobs/<이름>

final.mp4 음성을 faster-whisper(word_timestamps)로 다시 받아 적어서,
각 자막 덩어리의 첫 어절이 실제로 들리기 시작한 시각과 자막 표시 시각의 차이를 잰다.
- start  : 현재 자막(WhisperX 정렬) 시작 - 실제 발화 시작
- prop   : 예전 방식(글자 수 비율)이었다면의 시작 - 실제 발화 시작
"""
import difflib
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")


def norm(s):
    return re.sub(r"[^0-9A-Za-z가-힣]", "", s)


def main():
    job = Path(sys.argv[1])
    log = json.loads((job / "narration_timing.json").read_text(encoding="utf-8"))
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(job / "final.mp4"), "-ac", "1",
                          "-ar", "16000", "-f", "s16le", "-"], capture_output=True).stdout
    audio = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768

    from faster_whisper import WhisperModel
    model = WhisperModel(sys.argv[2] if len(sys.argv) > 2 else "medium", device="cpu",
                         compute_type="int8")
    words = []
    # 내레이션 구간만 잘라서 한국어로 인식 (영어 원본 구간 간섭 방지)
    segs = sorted({(e["seg_start"], e["seg_end"]) for e in log})
    for a, b in segs:
        part = audio[int(a * 16000):int(b * 16000)]
        res, _ = model.transcribe(part, language="ko", word_timestamps=True,
                                  condition_on_previous_text=False)
        for s in res:
            for w in s.words:
                words.append({"w": norm(w.word), "start": a + w.start})

    rows, errs, perrs = [], [], []
    for e in log:
        first = norm(e["text"].split()[0])
        cands = [w for w in words if e["seg_start"] - 0.05 <= w["start"] <= e["seg_end"]]
        best, score = None, 0.0
        for w in cands:
            r = difflib.SequenceMatcher(None, first, w["w"]).ratio()
            # 같은 점수면 자막 시각에 가까운 쪽
            if r > score + 1e-9 or (best and abs(r - score) < 1e-9 and
                                    abs(w["start"] - e["start"]) < abs(best["start"] - e["start"])):
                best, score = w, r
        if not best or score < 0.5:
            rows.append(f"  ?      ?       {e['text']}  (인식 단어 매칭 실패)")
            continue
        d, pd = e["start"] - best["start"], e["prop_start"] - best["start"]
        errs.append(abs(d))
        perrs.append(abs(pd))
        flag = "  ←" if abs(d) > 0.25 else ""
        rows.append(f"{d:+6.2f}s {pd:+6.2f}s  {e['text']}{flag}")

    print(f"{'WhisperX':>7} {'글자비율':>7}  자막 (+ 늦게 뜸 / - 먼저 뜸)")
    print("\n".join(rows))
    if errs:
        def stat(x):
            return f"평균 {np.mean(x):.3f}s, 최대 {np.max(x):.3f}s, 0.15s 이내 {np.mean(np.array(x) <= 0.15) * 100:.0f}%"
        print(f"\n측정 {len(errs)}/{len(log)}개")
        print(f"WhisperX 정렬 : {stat(errs)}")
        print(f"글자 수 비율  : {stat(perrs)}")


if __name__ == "__main__":
    main()
