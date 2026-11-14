"""Tri-Modal Subtitle, Script & Frame Sync Anchor Engine.

Solves the common 'off-sync SFX & subtitles' problem in automated Shorts pipelines by:
1. Parsing companion subtitle/script files (.srt, .vtt, .ass, or JSON word/line timestamps) if available.
2. Extracting 10ms speech energy onsets from the audio track via FFmpeg PCM decoding.
3. Re-snapping drifted subtitle timestamps to actual TTS/clip speech onsets (optional .synced.srt output).
4. Providing exact millisecond visual-cut + subtitle-pop + speech-onset anchors so Gemini's SFX cues
   snap cleanly to real frame transitions and highlighted keyword appearances.
"""

from __future__ import annotations

import array
import json
import math
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class SubtitleEvent:
    index: int
    start_sec: float
    end_sec: float
    text: str
    solo: bool = False
    icon: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _parse_srt_time(ts: str) -> float:
    ts = ts.strip().replace(",", ".")
    parts = ts.split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    if len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    return float(ts)


def _format_srt_time(sec: float) -> str:
    sec = max(0.0, sec)
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    ms = int(round((sec - math.floor(sec)) * 1000))
    if ms >= 1000:
        ms -= 1000
        s += 1
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def find_companion_subtitle_file(video_path: Path) -> Optional[Path]:
    """Auto-discover .srt, .ass, .vtt, or .json subtitle/timestamp files next to draft MP4."""
    for ext in [".srt", ".ass", ".vtt", ".subtitles.json", ".timestamps.json"]:
        cand = video_path.with_suffix(ext)
        if cand.is_file():
            return cand
    # Check common names in the same directory
    for name in ["subtitles.srt", "captions.srt", "caption.srt", "subtitles.ass", "timestamps.json"]:
        cand = video_path.parent / name
        if cand.is_file():
            return cand
    return None


def parse_subtitle_file(sub_path: Path) -> List[SubtitleEvent]:
    """Parse .srt, .vtt, .ass, or JSON timestamp arrays into SubtitleEvent objects."""
    raw = sub_path.read_text(encoding="utf-8", errors="ignore")
    suffix = sub_path.suffix.lower()

    if suffix == ".json":
        data = json.loads(raw)
        items = data.get("segments") or data.get("subtitles") or data.get("words") or (data if isinstance(data, list) else [])
        events: List[SubtitleEvent] = []
        for idx, item in enumerate(items, start=1):
            st = float(item.get("start", item.get("start_sec", 0.0)))
            ed = float(item.get("end", item.get("end_sec", st + 1.2)))
            txt = str(item.get("text", item.get("word", ""))).strip()
            if txt:
                events.append(SubtitleEvent(index=idx, start_sec=round(st, 3), end_sec=round(ed, 3), text=txt))
        return events

    if suffix == ".ass":
        events = []
        idx = 1
        for line in raw.splitlines():
            if line.startswith("Dialogue:"):
                parts = line.split(",", 9)
                if len(parts) >= 10:
                    st = _parse_srt_time(parts[1])
                    ed = _parse_srt_time(parts[2])
                    txt = re.sub(r"\{[^}]*\}", "", parts[9]).replace(r"\N", " ").strip()
                    if txt:
                        events.append(SubtitleEvent(index=idx, start_sec=round(st, 3), end_sec=round(ed, 3), text=txt))
                        idx += 1
        return events

    # Default .srt / .vtt parser
    events = []
    blocks = re.split(r"\r?\n\r?\n+", raw.strip())
    idx = 1
    time_re = re.compile(r"(\d{1,2}:\d{2}:\d{2}[,\.]\d{1,3}|\d{2}:\d{2}[,\.]\d{1,3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,\.]\d{1,3}|\d{2}:\d{2}[,\.]\d{1,3})")
    for block in blocks:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        match_line_idx = -1
        m = None
        for i, ln in enumerate(lines):
            m = time_re.search(ln)
            if m:
                match_line_idx = i
                break
        if m is None:
            continue
        st = _parse_srt_time(m.group(1))
        ed = _parse_srt_time(m.group(2))
        txt = " ".join(lines[match_line_idx + 1 :])
        txt = re.sub(r"<[^>]+>", "", txt).strip()
        if txt:
            events.append(SubtitleEvent(index=idx, start_sec=round(st, 3), end_sec=round(ed, 3), text=txt))
            idx += 1
    return events


def extract_speech_onsets_ffmpeg(media_path: Path, ffmpeg_bin: str = "ffmpeg") -> List[float]:
    """Detect exact 10ms speech phrase onset timestamps from audio waveform energy rises."""
    cmd = [
        ffmpeg_bin,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(media_path),
        "-f",
        "s16le",
        "-ac",
        "1",
        "-ar",
        "16000",
        "pipe:1",
    ]
    proc = subprocess.run(cmd, capture_output=True, check=False, timeout=40)
    if proc.returncode != 0 or not proc.stdout:
        return []

    raw = proc.stdout
    samples = array.array("h")
    samples.frombytes(raw[: len(raw) - (len(raw) % 2)])
    if not samples:
        return []

    win = 160  # 10ms @ 16kHz
    rms_db: List[float] = []
    for i in range(0, len(samples), win):
        chunk = samples[i : i + win]
        if not chunk:
            break
        sq = sum(s * s for s in chunk) / len(chunk)
        db = 20.0 * math.log10(max(math.sqrt(sq), 1.0) / 32768.0)
        rms_db.append(db)

    onsets: List[float] = []
    last_onset_idx = -25
    # Trigger onset when 10ms energy jumps >= 9dB over preceding 40ms floor and exceeds -36dBFS
    for idx in range(4, len(rms_db)):
        prev_floor = sum(rms_db[idx - 4 : idx]) / 4.0
        cur = rms_db[idx]
        if cur > -36.0 and (cur - prev_floor) >= 9.0 and (idx - last_onset_idx) >= 22:
            onsets.append(round(idx * 0.01, 3))
            last_onset_idx = idx
    return onsets


def snap_subtitles_to_speech_onsets(
    subtitles: List[SubtitleEvent],
    speech_onsets: List[float],
    max_shift_sec: float = 0.28,
) -> List[SubtitleEvent]:
    """Tighten drifted TTS/script subtitle start times onto real acoustic speech syllable onsets."""
    if not subtitles or not speech_onsets:
        return subtitles

    synced: List[SubtitleEvent] = []
    for ev in subtitles:
        nearest = min(speech_onsets, key=lambda o: abs(o - ev.start_sec))
        delta = nearest - ev.start_sec
        if abs(delta) <= max_shift_sec:
            dur = max(0.35, ev.end_sec - ev.start_sec)
            new_start = round(max(0.0, nearest), 3)
            new_end = round(new_start + dur, 3)
            synced.append(SubtitleEvent(index=ev.index, start_sec=new_start, end_sec=new_end, text=ev.text))
        else:
            synced.append(ev)

    # Prevent overlap between consecutive subtitles
    for i in range(len(synced) - 1):
        if synced[i].end_sec > synced[i + 1].start_sec:
            synced[i].end_sec = round(max(synced[i].start_sec + 0.2, synced[i + 1].start_sec - 0.02), 3)
    return synced


def write_srt_file(subtitles: List[SubtitleEvent], out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines: List[str] = []
    for idx, ev in enumerate(subtitles, start=1):
        lines.append(str(idx))
        lines.append(f"{_format_srt_time(ev.start_sec)} --> {_format_srt_time(ev.end_sec)}")
        lines.append(ev.text)
        lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def snap_cue_timestamp_to_anchors(
    raw_ts_sec: float,
    trigger_type: str,
    visual_cuts: List[float],
    subtitles: List[SubtitleEvent],
    speech_onsets: List[float],
    snap_window_sec: float = 0.18,
) -> Tuple[float, str, str]:
    """Snap a Gemini-proposed SFX timestamp to the closest exact frame cut or subtitle/speech onset."""
    # Priority 1: For scene_cut / mood_shift, prefer exact FFmpeg visual cut timestamp
    if trigger_type in {"scene_cut", "mood_shift"} and visual_cuts:
        nearest_cut = min(visual_cuts, key=lambda c: abs(c - raw_ts_sec))
        if abs(nearest_cut - raw_ts_sec) <= snap_window_sec:
            return round(nearest_cut, 3), "visual_cut", ""

    # Priority 2: For caption_pop / money_stat / hook_0_3s / clip_reaction, prefer exact subtitle onset
    if subtitles:
        nearest_sub = min(subtitles, key=lambda s: abs(s.start_sec - raw_ts_sec))
        if abs(nearest_sub.start_sec - raw_ts_sec) <= snap_window_sec * 1.25:
            return round(nearest_sub.start_sec, 3), "subtitle_onset", nearest_sub.text

    # Priority 3: Check visual cut for any other trigger within window
    if visual_cuts:
        nearest_cut = min(visual_cuts, key=lambda c: abs(c - raw_ts_sec))
        if abs(nearest_cut - raw_ts_sec) <= snap_window_sec:
            return round(nearest_cut, 3), "visual_cut", ""

    # Priority 4: Snap to acoustic speech onset if very close (<= 120ms)
    if speech_onsets:
        nearest_onset = min(speech_onsets, key=lambda o: abs(o - raw_ts_sec))
        if abs(nearest_onset - raw_ts_sec) <= 0.12:
            return round(nearest_onset, 3), "speech_onset", ""

    return round(raw_ts_sec, 3), "gemini_vision", ""
