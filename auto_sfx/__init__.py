"""Automated Multimodal SFX Director package for 60SEC_YOUTUBE_AUTO_SHORT."""

from .cataloger import SFXCatalogManager
from .config import SFXConfig, is_auto_sfx_enabled
from .cuesheet import generate_sfx_cuesheet
from .director import apply_auto_sfx_if_enabled, run_edl_auto_sfx_stage
from .matcher import resolve_cuesheet
from .mixer import mix_sfx_into_video
from .sync_anchor import parse_subtitle_file, snap_subtitles_to_speech_onsets

__all__ = [
    "SFXConfig",
    "is_auto_sfx_enabled",
    "SFXCatalogManager",
    "generate_sfx_cuesheet",
    "resolve_cuesheet",
    "mix_sfx_into_video",
    "apply_auto_sfx_if_enabled",
    "run_edl_auto_sfx_stage",
    "parse_subtitle_file",
    "snap_subtitles_to_speech_onsets",
]
