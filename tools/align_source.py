"""원본 대사 전사(transcript.json)를 WhisperX 로 어절 단위 정렬 → transcript_words.json

.venv-whisperx 파이썬으로 실행:  python align_source.py <job_dir> [device] [lang]
출력: {"<id>": [{"w": 단어, "s": 시작, "e": 끝}, ...]}  (id 는 transcript.json 과 동일)
정렬 못 한 단어는 같은 줄 안에서 앞뒤 사이를 보간.
"""
import json
import sys
from pathlib import Path


def main():
    job = Path(sys.argv[1])
    device = sys.argv[2] if len(sys.argv) > 2 else "cpu"
    lang = sys.argv[3] if len(sys.argv) > 3 else "en"
    import whisperx

    tr = json.load(open(job / "transcript.json", encoding="utf-8"))
    audio = whisperx.load_audio(str(job / "source.mp4"))
    model, meta = whisperx.load_align_model(language_code=lang, device=device)
    segs = [{"text": t["text"], "start": t["start"], "end": t["end"]} for t in tr]
    out = {}
    # 줄 단위로 정렬해야 id 가 섞이지 않음 (한 번에 넣으면 whisperx 가 문장 단위로 재분할함)
    for t, s in zip(tr, segs):
        try:
            res = whisperx.align([s], model, meta, audio, device, return_char_alignments=False)
            words = [w for seg in res["segments"] for w in seg.get("words", [])]
        except Exception:
            words = []
        ws = [{"w": w.get("word", ""), "s": w.get("start"), "e": w.get("end")} for w in words]
        # 보간: 시작/끝 없는 단어
        known = [(i, w) for i, w in enumerate(ws) if w["s"] is not None]
        if not known:
            ws = [{"w": t["text"], "s": t["start"], "e": t["end"]}]
        else:
            for i, w in enumerate(ws):
                if w["s"] is None:
                    prev = max((k for k, _ in known if k < i), default=None)
                    nxt = min((k for k, _ in known if k > i), default=None)
                    lo = ws[prev]["e"] if prev is not None else t["start"]
                    hi = ws[nxt]["s"] if nxt is not None else t["end"]
                    w["s"], w["e"] = lo, max(lo, hi)
        out[str(t["id"])] = [{"w": w["w"], "s": round(w["s"], 3), "e": round(w["e"], 3)} for w in ws]
    json.dump(out, open(job / "transcript_words.json", "w", encoding="utf-8"), ensure_ascii=False)
    print(f"aligned {len(out)} lines")


if __name__ == "__main__":
    main()
