"""1단계: 원본 확보(유튜브 URL 또는 로컬 파일) + 구간 자르기 + 영어 전사."""
import importlib.util
import shutil
import sys
from pathlib import Path

import numpy as np

from .common import ffmpeg, run, write_json


def _yt_dlp_cmd() -> list[str]:
    exe = shutil.which("yt-dlp")
    if exe:
        return [exe]
    if importlib.util.find_spec("yt_dlp") is not None:
        return [sys.executable, "-m", "yt_dlp"]
    raise RuntimeError(
        "yt-dlp 가 설치되어 있지 않습니다. 터미널에서 'pip install yt-dlp' 를 한 번 실행하거나 로컬 mp4 파일 경로를 입력해 주세요."
    )


def fetch(src, job: Path, start=None, end=None):
    """src(URL 또는 파일)를 job/source.mp4 로 준비. start/end(초)가 있으면 그 구간만."""
    job = Path(job)
    job.mkdir(parents=True, exist_ok=True)
    raw = job / "raw.mp4"
    src_str = str(src).strip()
    if Path(src_str).is_file():
        shutil.copy(src_str, raw)
    else:
        cmd = _yt_dlp_cmd() + [
            "--no-warnings",
            "--no-playlist",
            "-f",
            "bv*[height<=1080]+ba/b",
            "--merge-output-format",
            "mp4",
            "-o",
            str(raw),
            src_str,
        ]
        run(cmd)
    out = job / "source.mp4"
    args = []
    if start is not None:
        args += ["-ss", str(start)]
    args += ["-i", raw]
    if end is not None:
        dur = float(end) - float(start or 0)
        if dur <= 0:
            raise ValueError("끝 시각(초)은 시작 시각(초)보다 커야 합니다.")
        args += ["-t", str(dur)]
    # EDL 렌더러(1920x1080 기준 크롭·얼굴 추적)와 100% 호환되도록 1920x1080 30fps 고정 재인코딩
    vf = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30,format=yuv420p"
    ffmpeg(
        *args,
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        "-ac",
        "2",
        out,
    )
    raw.unlink(missing_ok=True)
    return out


def _proportional_en_words(text: str, start: float, end: float) -> list[dict]:
    tokens = [t for t in text.strip().split() if t]
    if not tokens:
        return []
    dur = max(0.05, float(end) - float(start))
    weights = [max(1, len(t)) for t in tokens]
    total_w = sum(weights) or 1
    out, cur = [], float(start)
    for tok, w in zip(tokens, weights):
        d = dur * (w / total_w)
        out.append({"w": tok, "s": round(cur, 3), "e": round(cur + d, 3)})
        cur += d
    return out


def transcribe(video: Path, job: Path, model_name="small", language="en"):
    """faster-whisper 로 원본 대사 전사 → transcript.json [{id,start,end,text}] + transcript_words.json."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "faster-whisper 가 설치되어 있지 않습니다. 'pip install faster-whisper' 설치 후 다시 시도해 주세요."
        ) from exc

    # PyAV 버전 호환 문제를 피하려고 ffmpeg 로 직접 디코딩
    pcm = run_bytes([
        "ffmpeg", "-v", "error", "-i", str(video), "-ac", "1", "-ar", "16000", "-f", "s16le", "-"
    ])
    audio = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segs, _ = model.transcribe(
        audio,
        language=language or None,
        vad_filter=True,
        word_timestamps=True,
        condition_on_previous_text=False,
    )
    items: list[dict] = []
    words_by_id: dict[str, list[dict]] = {}
    idx = 0
    for s in segs:
        txt = (s.text or "").strip()
        if not txt:
            continue
        seg_start = round(float(s.start), 2)
        seg_end = round(max(float(s.end), seg_start + 0.06), 2)
        items.append({"id": idx, "start": seg_start, "end": seg_end, "text": txt})
        seg_words: list[dict] = []
        for w in (getattr(s, "words", None) or []):
            wt = (getattr(w, "word", "") or "").strip()
            if not wt:
                continue
            ws = round(max(0.0, float(w.start)), 3)
            we = round(max(ws + 0.02, float(w.end)), 3)
            seg_words.append({"w": wt, "s": ws, "e": we})
        if not seg_words:
            seg_words = _proportional_en_words(txt, seg_start, seg_end)
        words_by_id[str(idx)] = seg_words
        idx += 1

    write_json(job / "transcript.json", items)
    write_json(job / "transcript_words.json", words_by_id)
    return items


def run_bytes(cmd):
    import subprocess

    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace")[-1500:])
    return r.stdout
