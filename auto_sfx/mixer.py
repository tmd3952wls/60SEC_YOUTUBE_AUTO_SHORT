"""Audio Volume Balancing (Sidechain Ducking) & Peak-Aligned FFmpeg Mixer (Requirement 5).

Mixes resolved SFX cues onto a draft rendered MP4 (preserving video stream losslessly via -c:v copy)
with millisecond peak alignment (atrim + adelay), -12dB ~ -18dB gain staging, and dynamic sidechain
ducking under narration speech so voiceover clarity is never masked.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import List

from .config import SFXConfig
from .models import ResolvedSFXCue

logger = logging.getLogger("auto_sfx.mixer")


def _has_audio_stream(video_path: Path, ffprobe_bin: str = "ffprobe") -> bool:
    cmd = [
        ffprobe_bin,
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_name",
        "-of",
        "csv=p=0",
        str(video_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=15)
    return proc.returncode == 0 and bool(proc.stdout.strip())


def build_ffmpeg_sfx_command(
    input_video: Path,
    output_video: Path,
    resolved_cues: List[ResolvedSFXCue],
    video_duration_sec: float,
    config: SFXConfig,
    has_base_audio: bool = True,
    filter_script_path: Path | None = None,
) -> List[str]:
    """Construct the exact FFmpeg CLI command with filter_complex for peak-synced SFX + ducking."""
    cmd: List[str] = [
        config.ffmpeg_bin,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(input_video),
    ]

    for item in resolved_cues:
        cmd.extend(["-i", item.sfx.absolute_path])

    filter_chains: List[str] = []
    sfx_labels: List[str] = []

    for idx, item in enumerate(resolved_cues, start=1):
        max_len = round(max(0.25, item.cue.max_duration_sec), 3)
        trim_end = round(item.trim_start_sec + max_len, 3)
        fade_out_start = round(max(0.05, max_len - 0.12), 3)
        delay_ms = max(0, item.insert_delay_ms)
        gain_db = item.effective_gain_db

        chain_parts = [
            f"[{idx}:a]aformat=sample_rates=48000:channel_layouts=stereo",
            f"atrim=start={item.trim_start_sec:.4f}:end={trim_end:.4f}",
            "asetpts=PTS-STARTPTS",
            f"afade=t=out:st={fade_out_start:.3f}:d=0.12",
            f"volume={gain_db:.2f}dB",
        ]
        if delay_ms > 0:
            chain_parts.append(f"adelay={delay_ms}|{delay_ms}")
        chain_parts.append(f"apad=whole_dur={video_duration_sec:.3f}[sfx_{idx}]")
        filter_chains.append(",".join(chain_parts))
        sfx_labels.append(f"[sfx_{idx}]")

    if len(sfx_labels) == 1:
        filter_chains.append(f"{sfx_labels[0]}anull[sfx_bus]")
    else:
        joined = "".join(sfx_labels)
        filter_chains.append(
            f"{joined}amix=inputs={len(sfx_labels)}:duration=first:dropout_transition=0:normalize=0[sfx_bus]"
        )

    if has_base_audio:
        filter_chains.append(
            f"[0:a]aformat=sample_rates=48000:channel_layouts=stereo,apad=whole_dur={video_duration_sec:.3f},atrim=0:{video_duration_sec:.3f}[base_norm]"
        )
        if config.enable_sidechain_ducking and any(c.cue.duck_under_speech for c in resolved_cues):
            # Split base narration+BGM into [voice_main] and [sc_key]; gentle cushion since K-weighted voice-relative calibration already balanced SFX
            filter_chains.append("[base_norm]asplit=2[voice_main][sc_key]")
            filter_chains.append(
                "[sfx_bus][sc_key]sidechaincompress=threshold=0.12:ratio=1.6:attack=15:release=160:makeup=1[sfx_ducked]"
            )
            filter_chains.append(
                "[voice_main][sfx_ducked]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
                "alimiter=limit=0.95:attack=5:release=50[final_a]"
            )
        else:
            filter_chains.append(
                "[base_norm][sfx_bus]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
                "alimiter=limit=0.95:attack=5:release=50[final_a]"
            )
    else:
        filter_chains.append(
            f"[sfx_bus]atrim=0:{video_duration_sec:.3f},alimiter=limit=0.95:attack=5:release=50[final_a]"
        )

    filter_complex = ";".join(filter_chains)
    if filter_script_path is not None:
        filter_script_path.parent.mkdir(parents=True, exist_ok=True)
        filter_script_path.write_text(filter_complex, encoding="utf-8")
        # FFmpeg 7+/8+ uses `-/filter_complex <file>` when reading filtergraph from file
        cmd.extend(["-/filter_complex", str(filter_script_path)])
    else:
        cmd.extend(["-filter_complex", filter_complex])
    cmd.extend(
        [
            "-map",
            "0:v:0",
            "-map",
            "[final_a]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            str(output_video),
        ]
    )
    return cmd


def mix_sfx_into_video(
    input_video: Path,
    output_video: Path,
    resolved_cues: List[ResolvedSFXCue],
    video_duration_sec: float,
    config: SFXConfig,
) -> Path:
    """Render final MP4 with peak-aligned SFX and dynamic narration ducking."""
    output_video.parent.mkdir(parents=True, exist_ok=True)

    if not resolved_cues:
        logger.info("No resolved SFX cues to mix; copying draft video unchanged to %s", output_video)
        if input_video.resolve() != output_video.resolve():
            shutil.copy2(input_video, output_video)
        return output_video

    has_audio = _has_audio_stream(input_video, ffprobe_bin=config.ffprobe_bin)
    # Windows CreateProcessW supports 32,767 chars (~180 cues); only spill to file on extreme cue counts
    script_file = output_video.with_name(f"._sfx_fc_{output_video.stem}.txt") if len(resolved_cues) >= 90 else None
    try:
        cmd = build_ffmpeg_sfx_command(
            input_video=input_video,
            output_video=output_video,
            resolved_cues=resolved_cues,
            video_duration_sec=video_duration_sec,
            config=config,
            has_base_audio=has_audio,
            filter_script_path=script_file,
        )
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=180)
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg SFX mixing failed (exit {proc.returncode}):\n{proc.stderr}")
    finally:
        if script_file is not None:
            script_file.unlink(missing_ok=True)

    logger.info("Successfully mixed %d SFX cues into %s", len(resolved_cues), output_video)
    return output_video
