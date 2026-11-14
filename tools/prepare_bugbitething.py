"""Download & prepare jobs/bugbitething:
1) yt-dlp 1080p download -> source_raw.mp4
2) 1920x1080 30fps CFR -> source.mp4
3) Stereo broadcast BGM suppression -> source_vocals.wav
4) Word-exact faster-whisper transcription -> transcript.json & transcript_words.json
5) Fine scene cut detection -> cuts_fine.json
"""
import json
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf
from faster_whisper import WhisperModel
from scipy.signal import istft, stft

ROOT = Path(__file__).resolve().parent.parent
JOB = ROOT / "jobs" / "bugbitething"
JOB.mkdir(parents=True, exist_ok=True)

URL = "https://www.youtube.com/watch?v=lfzoGrzFn2g"
RAW = JOB / "source_raw.mp4"
SRC = JOB / "source.mp4"
VOC = JOB / "source_vocals.wav"
TR_JSON = JOB / "transcript.json"
WORDS_JSON = JOB / "transcript_words.json"
CUTS_FINE = JOB / "cuts_fine.json"


def download_1080p():
    if RAW.exists() and RAW.stat().st_size > 10_000_000:
        print("source_raw.mp4 already exists:", RAW.stat().st_size)
        return
    print("Downloading 1080p source_raw.mp4 via yt-dlp...")
    subprocess.run(
        [
            "yt-dlp",
            "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]",
            "--merge-output-format", "mp4",
            "-o", str(RAW),
            URL,
        ],
        check=True,
    )
    print("Downloaded source_raw.mp4:", RAW.stat().st_size)


def ensure_cfr_source():
    if SRC.exists() and SRC.stat().st_size > 10_000_000:
        print("source.mp4 already exists:", SRC.stat().st_size)
        return
    print("Normalizing to 1920x1080 30fps CFR source.mp4...")
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(RAW),
            "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-g", "30", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            str(SRC),
        ],
        check=True,
    )
    print("source.mp4 ready:", SRC.stat().st_size)


def make_source_vocals():
    if VOC.exists() and VOC.stat().st_size > 10_000_000:
        print("source_vocals.wav already exists:", VOC.stat().st_size)
        return
    print("Extracting stereo audio and suppressing broadcast BGM -> source_vocals.wav...")
    sr = 48000
    pcm = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(SRC), "-ac", "2", "-ar", str(sr), "-f", "f32le", "-"],
        capture_output=True, check=True,
    ).stdout
    stereo = np.frombuffer(pcm, dtype=np.float32).reshape(-1, 2)
    mid = 0.5 * (stereo[:, 0] + stereo[:, 1])
    side = 0.5 * (stereo[:, 0] - stereo[:, 1])

    f, _, Z_mid = stft(mid, fs=sr, nperseg=2048, noverlap=1536)
    _, _, Z_side = stft(side, fs=sr, nperseg=2048, noverlap=1536)

    mag_m = np.abs(Z_mid) + 1e-8
    mag_s = np.abs(Z_side) + 1e-8
    pan_mask = np.clip(1.0 - 1.35 * (mag_s / mag_m), 0.12, 1.0) ** 1.4

    freq_weight = np.ones_like(f)[:, None]
    freq_weight[f < 95] = 0.10
    freq_weight[(f >= 95) & (f < 140)] = 0.55
    freq_weight[f > 8500] = 0.35

    Z_voc = Z_mid * pan_mask * freq_weight
    _, voc = istft(Z_voc, fs=sr, nperseg=2048, noverlap=1536)
    voc = voc[: len(mid)].astype(np.float32)
    peak = float(np.max(np.abs(voc)) + 1e-8)
    if peak > 0.95:
        voc *= 0.95 / peak
    voc_st = np.column_stack([voc, voc])
    sf.write(str(VOC), voc_st, sr, subtype="PCM_16")
    print("source_vocals.wav ready:", VOC.stat().st_size)


def transcribe_word_exact():
    if TR_JSON.exists() and WORDS_JSON.exists():
        print("transcript.json & transcript_words.json already exist.")
        return
    print("Running faster-whisper (small, word_timestamps=True) on 16kHz vocal track...")
    pcm16 = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(VOC), "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
        capture_output=True, check=True,
    ).stdout
    audio16 = np.frombuffer(pcm16, dtype=np.float32).copy()

    wm = WhisperModel("small", device="cpu", compute_type="int8")
    segments, _ = wm.transcribe(
        audio16,
        language="en",
        word_timestamps=True,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 250},
    )
    tr_rows = []
    words_map = {}
    for seg in segments:
        txt = seg.text.strip()
        if not txt:
            continue
        sid = len(tr_rows)
        tr_rows.append({
            "id": sid,
            "start": round(float(seg.start), 3),
            "end": round(float(seg.end), 3),
            "text": txt,
        })
        wlist = []
        for w in (seg.words or []):
            wt = w.word.strip()
            if wt:
                wlist.append({
                    "w": wt,
                    "s": round(float(w.start), 3),
                    "e": round(float(w.end), 3),
                })
        if not wlist:
            wlist = [{"w": txt, "s": round(float(seg.start), 3), "e": round(float(seg.end), 3)}]
        words_map[str(sid)] = wlist

    TR_JSON.write_text(json.dumps(tr_rows, ensure_ascii=False, indent=1), encoding="utf-8")
    WORDS_JSON.write_text(json.dumps(words_map, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Transcribed {len(tr_rows)} segments with exact word timestamps!")


def make_cuts_fine():
    if CUTS_FINE.exists():
        print("cuts_fine.json already exists.")
        return
    import sys
    sys.path.insert(0, str(ROOT))
    from shorts.scenes import detect_cuts
    cuts = sorted(detect_cuts(SRC, 0.25))
    CUTS_FINE.write_text(json.dumps(cuts, indent=1), encoding="utf-8")
    print(f"Detected {len(cuts)} fine scene cuts -> cuts_fine.json")


if __name__ == "__main__":
    download_1080p()
    ensure_cfr_source()
    make_source_vocals()
    transcribe_word_exact()
    make_cuts_fine()
