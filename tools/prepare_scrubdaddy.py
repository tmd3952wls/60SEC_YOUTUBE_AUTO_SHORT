"""Prepare jobs/scrubdaddy: 1920x1080 30fps CFR source.mp4, BGM-suppressed source_vocals.wav, and word-exact Whisper transcript."""
import json
import subprocess
from pathlib import Path
import numpy as np
import soundfile as sf
from scipy.signal import stft, istft
from faster_whisper import WhisperModel

ROOT = Path(__file__).resolve().parent.parent
JOB = ROOT / "jobs" / "scrubdaddy"
RAW = JOB / "source_raw.mp4"
SRC = JOB / "source.mp4"
VOC = JOB / "source_vocals.wav"
TR_JSON = JOB / "transcript.json"
WORDS_JSON = JOB / "transcript_words.json"


def ensure_cfr_source():
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate,avg_frame_rate", "-of", "json", str(RAW)],
        capture_output=True, text=True, check=True,
    ).stdout
    info = json.loads(probe)["streams"][0]
    print("Raw stream info:", info)
    if not SRC.exists():
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
    """Suppress stereo Shark Tank broadcast BGM while preserving natural center-panned dialogue."""
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
    # Broadcast dialogue sits in center (mid >> side); stereo BGM has strong side energy and sub-110Hz / >7.5kHz energy
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
    for idx, seg in enumerate(segments):
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


if __name__ == "__main__":
    ensure_cfr_source()
    make_source_vocals()
    transcribe_word_exact()
