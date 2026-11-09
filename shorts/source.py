"""1단계: 원본 확보(유튜브 URL 또는 로컬 파일) + 구간 자르기 + 영어 전사."""
import shutil
from pathlib import Path

import numpy as np

from .common import ffmpeg, run, write_json


def fetch(src, job: Path, start=None, end=None):
    """src(URL 또는 파일)를 job/source.mp4 로 준비. start/end(초)가 있으면 그 구간만."""
    raw = job / "raw.mp4"
    if Path(src).exists():
        shutil.copy(src, raw)
    else:
        run(["yt-dlp", "-q", "--no-warnings", "--no-playlist",
             "-f", "bv*[height<=1080]+ba/b", "--merge-output-format", "mp4",
             "-o", str(raw), src])
    out = job / "source.mp4"
    args = []
    if start is not None:
        args += ["-ss", str(start)]
    args += ["-i", raw]
    if end is not None:
        args += ["-t", str(end - (start or 0))]
    # 정확한 컷을 위해 재인코딩(키프레임 문제 방지), 30fps 고정
    ffmpeg(*args, "-vf", "fps=30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", out)
    raw.unlink(missing_ok=True)
    return out


def transcribe(video: Path, job: Path, model_name="small", language="en"):
    """faster-whisper 로 원본 대사 전사 → transcript.json [{id,start,end,text}]."""
    from faster_whisper import WhisperModel

    # PyAV 버전 호환 문제를 피하려고 ffmpeg 로 직접 디코딩
    pcm = run_bytes(["ffmpeg", "-v", "error", "-i", str(video), "-ac", "1", "-ar", "16000",
                     "-f", "s16le", "-"])
    audio = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segs, _ = model.transcribe(audio, language=language, vad_filter=True,
                               condition_on_previous_text=False)
    items = [{"id": i, "start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()}
             for i, s in enumerate(segs)]
    write_json(job / "transcript.json", items)
    return items


def run_bytes(cmd):
    import subprocess
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace")[-1500:])
    return r.stdout
