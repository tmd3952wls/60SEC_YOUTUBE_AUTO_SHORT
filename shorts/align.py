"""내레이션 자막 타이밍: WhisperX 강제 정렬 결과(어절별 시간)를 캐시와 함께 제공."""
import json
import subprocess
import tempfile
from pathlib import Path

from .common import ROOT


def ensure_words(job, cfg):
    """원본 대사의 어절별 시간(transcript_words.json). 없으면 WhisperX 로 만든다."""
    p = Path(job) / "transcript_words.json"
    if not p.exists():
        py = ROOT / cfg.get("align", {}).get("python", ".venv-whisperx/Scripts/python.exe")
        if py.exists():
            print("  원본 대사 어절 정렬 (WhisperX)...")
            r = subprocess.run([str(py), "-I", str(ROOT / "tools" / "align_source.py"), str(job),
                                cfg.get("align", {}).get("device", "cpu"), "en"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            if r.returncode != 0:
                print("  ⚠ 어절 정렬 실패 → 줄 단위로 진행\n" + r.stderr[-800:])
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _cache(wav):
    return Path(wav).with_suffix(".align.json")


def align_all(items, cfg):
    """items: [(wav, text)] → {wav: words}. 정렬 불가 시 None 값(호출 측에서 글자 수 비율로 대체)."""
    acfg = cfg.get("align", {})
    result, todo = {}, []
    for wav, text in items:
        c = _cache(wav)
        if c.exists():
            d = json.loads(c.read_text(encoding="utf-8"))
            if d.get("text") == text:
                result[str(wav)] = d["words"]
                continue
        todo.append({"wav": str(wav), "text": text})
    if todo and acfg.get("enabled", True):
        py = ROOT / acfg.get("python", ".venv-whisperx/Scripts/python.exe")
        if not py.exists():
            print(f"  ⚠ WhisperX 환경 없음({py}) → 글자 수 비율 타이밍 사용")
        else:
            with tempfile.TemporaryDirectory() as td:
                src, dst = Path(td) / "in.json", Path(td) / "out.json"
                src.write_text(json.dumps(todo, ensure_ascii=False), encoding="utf-8")
                r = subprocess.run([str(py), "-I", str(ROOT / "tools" / "align_narration.py"),
                                    str(src), str(dst), acfg.get("device", "cpu")],
                                   capture_output=True, text=True, encoding="utf-8", errors="replace")
                if r.returncode != 0:
                    print("  ⚠ WhisperX 정렬 실패 → 글자 수 비율 타이밍 사용\n" + r.stderr[-1500:])
                else:
                    by_wav = {it["wav"]: it for it in todo}
                    for o in json.loads(dst.read_text(encoding="utf-8")):
                        _cache(o["wav"]).write_text(json.dumps(
                            {"text": by_wav[o["wav"]]["text"], "words": o["words"]},
                            ensure_ascii=False, indent=1), encoding="utf-8")
                        result[o["wav"]] = o["words"]
    for wav, _ in items:
        result.setdefault(str(wav), None)
    return result


def chunk_times(chunks, words, tts_dur, lead=0.05):
    """화면 덩어리(어절 묶음)별 (시작, 끝). 다음 덩어리 시작까지 유지해 깜빡임 방지."""
    spans, k = [], 0
    for c in chunks:
        n = len(c.split())
        ws = words[k:k + n]
        spans.append([ws[0]["start"], ws[-1]["end"]])
        k += n
    out = []
    for i, (a, b) in enumerate(spans):
        start = 0.0 if i == 0 else max(0.0, a - lead)
        end = spans[i + 1][0] - lead if i + 1 < len(spans) else tts_dur
        out.append((start, max(end, b if i + 1 == len(spans) else end)))
    return out


def proportional_times(chunks, tts_dur):
    """정렬 실패 시 대체: 글자 수 비율."""
    total = sum(len(c) for c in chunks) or 1
    out, t = [], 0.0
    for c in chunks:
        d = tts_dur * len(c) / total
        out.append((t, t + d))
        t += d
    return out
