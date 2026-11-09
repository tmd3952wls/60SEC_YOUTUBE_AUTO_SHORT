"""WhisperX 강제 정렬: 알고 있는 대본 텍스트를 실제 TTS 음성에 맞춰 어절별 시간 추출.

.venv-whisperx 의 파이썬으로 실행된다 (메인 환경과 분리).
  python align_narration.py <입력.json> <출력.json> [device]
입력: [{"wav": 경로, "text": 대본}, ...]
출력: [{"wav":..., "duration": 초, "words": [{"word", "start", "end", "aligned"}]}, ...]
  - 어절은 text.split() 과 1:1 로 대응
  - 정렬 모델이 못 잡은 어절(숫자·영문 등)은 앞뒤 어절 사이를 글자 수 비율로 보간 (aligned=false)
"""
import json
import sys


def interpolate(words, dur):
    n = len(words)
    i = 0
    while i < n:
        if words[i]["start"] is not None:
            i += 1
            continue
        j = i
        while j < n and words[j]["start"] is None:
            j += 1
        lo = words[i - 1]["end"] if i > 0 else 0.0
        hi = words[j]["start"] if j < n else dur
        total = sum(len(w["word"]) for w in words[i:j]) or 1
        t = lo
        for w in words[i:j]:
            d = (hi - lo) * len(w["word"]) / total
            w["start"], w["end"] = round(t, 3), round(t + d, 3)
            t += d
        i = j
    return words


def main():
    src, dst = sys.argv[1], sys.argv[2]
    device = sys.argv[3] if len(sys.argv) > 3 else "cpu"
    import whisperx

    items = json.load(open(src, encoding="utf-8"))
    model, meta = whisperx.load_align_model(language_code="ko", device=device)
    out = []
    for it in items:
        audio = whisperx.load_audio(it["wav"])
        dur = len(audio) / 16000
        tokens = it["text"].split()
        res = whisperx.align([{"text": " ".join(tokens), "start": 0.0, "end": dur}],
                             model, meta, audio, device, return_char_alignments=False)
        got = [w for s in res["segments"] for w in s.get("words", [])]
        words = []
        # whisperx 는 공백 기준으로 어절을 나누므로 순서대로 1:1 대응
        for k, tok in enumerate(tokens):
            w = got[k] if k < len(got) else {}
            ok = "start" in w and "end" in w
            words.append({"word": tok, "start": round(w["start"], 3) if ok else None,
                          "end": round(w["end"], 3) if ok else None, "aligned": ok})
        out.append({"wav": it["wav"], "duration": round(dur, 3), "words": interpolate(words, dur)})
    json.dump(out, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
