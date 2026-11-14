"""렌더링 결과물(full_vN.mp4) 시각 컨택트 시트 생성 및 음향(LUFS·내레이션 F0 Hz) 정밀 검증 도구."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import librosa
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def make_contact_sheet(video_path: Path, out_jpg: Path, cols: int = 4, rows: int = 4) -> float:
    dur = float(
        subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video_path)],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    )
    n = cols * rows
    times = [round((i + 0.5) * dur / n, 2) for i in range(n)]
    tw, th = 270, 480
    canvas = Image.new("RGB", (cols * tw, rows * th), (18, 18, 18))
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/malgunbd.ttf", 20)
    except Exception:
        font = ImageFont.load_default()

    for idx, t in enumerate(times):
        raw = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-ss",
                f"{t:.2f}",
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                "-vf",
                f"scale={tw}:{th}",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "-",
            ],
            capture_output=True,
            check=True,
        ).stdout
        if len(raw) == tw * th * 3:
            im = Image.frombytes("RGB", (tw, th), raw)
            r, c = divmod(idx, cols)
            x0, y0 = c * tw, r * th
            canvas.paste(im, (x0, y0))
            draw.rectangle([x0 + 4, y0 + 4, x0 + 92, y0 + 30], fill=(0, 0, 0))
            draw.text((x0 + 8, y0 + 5), f"{t:5.2f}s", fill=(255, 230, 80), font=font)

    canvas.save(out_jpg, quality=90)
    return dur


def measure_audio_metrics(job_dir: Path, video_path: Path) -> dict:
    # 1. Measure stream specs
    probe = json.loads(
        subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels:format=duration",
                "-of",
                "json",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    # 2. Measure narration F0 Hz on body.mp4 over narration items
    exp_path = job_dir / "edl_tmp" / "export.json"
    body_path = job_dir / "edl_tmp" / "body.mp4"
    narr_f0_median = None
    narr_f0_p25 = None
    if exp_path.exists() and body_path.exists():
        exp = json.loads(exp_path.read_text(encoding="utf-8"))
        pcm = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(body_path), "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
            capture_output=True,
            check=True,
        ).stdout
        y = np.frombuffer(pcm, np.float32)
        f0_all = []
        for it in exp.get("items", []):
            if it.get("type") == "narration":
                a = int(float(it["t0"]) * 16000)
                b = int((float(it["t0"]) + float(it["dur"])) * 16000)
                seg = y[a:b]
                if len(seg) > 1600:
                    f0, voiced, _ = librosa.pyin(seg, fmin=65, fmax=320, sr=16000)
                    valid = f0[voiced & ~np.isnan(f0)]
                    if len(valid):
                        f0_all.append(valid)
        if f0_all:
            cat = np.concatenate(f0_all)
            narr_f0_median = round(float(np.median(cat)), 1)
            narr_f0_p25 = round(float(np.percentile(cat, 25)), 1)

    return {
        "duration_sec": round(float(probe["format"]["duration"]), 2),
        "streams": probe["streams"],
        "narration_f0_median_hz": narr_f0_median,
        "narration_f0_p25_hz": narr_f0_p25,
    }


def main():
    job_dir = Path(sys.argv[1])
    video_name = sys.argv[2] if len(sys.argv) > 2 else "full_v1.mp4"
    video_path = job_dir / video_name
    out_jpg = job_dir / f"{video_path.stem}_contact_sheet.jpg"
    make_contact_sheet(video_path, out_jpg)
    metrics = measure_audio_metrics(job_dir, video_path)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    print(f"Saved contact sheet: {out_jpg}")


if __name__ == "__main__":
    main()
