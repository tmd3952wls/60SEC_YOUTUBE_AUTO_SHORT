"""Configuration, zero-billing backends, 해외쇼쇼 SFX presets, and ★ favorites store."""

from __future__ import annotations

import copy
import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Set

REPO_ROOT = Path(__file__).resolve().parent.parent

SFX_STYLE_PRESETS: Dict[str, Dict[str, Any]] = {
    "clean": {
        "id": "clean",
        "label_ko": "깔끔형",
        "badge_ko": "대사 집중 · 분당 ~10개 · -16.5dB",
        "desc_ko": "자잘한 전환음은 줄이고 초반 3초 훅·핵심 매출·결말 반전만 또렷하게 받쳐 줍니다.",
        "default_sfx_db": -16.5,
        "min_sfx_db": -18.5,
        "max_sfx_db": -14.0,
        "hook_db": -14.8,
        "accent_db": -15.5,
        "cut_db": -17.2,
        "min_cue_gap_sec": 2.6,
        "cut_spacing_sec": 6.2,
        "max_cues_per_minute": 10,
        "include_yellow_pops": False,
        "include_solo_pops": False,
        "include_secondary_money": False,
        "hero_swell_lead_in": False,
    },
    "balanced": {
        "id": "balanced",
        "label_ko": "해외쇼쇼 표준",
        "badge_ko": "레퍼런스 밸런스 · 분당 ~18개 · -15.0dB",
        "desc_ko": "해외쇼쇼 레퍼런스 쇼츠 문법 그대로 훅·원화 매출·단독 감탄사·3초 컷 전환을 균형 있게 배치합니다.",
        "default_sfx_db": -15.0,
        "min_sfx_db": -18.0,
        "max_sfx_db": -12.0,
        "hook_db": -13.5,
        "accent_db": -14.0,
        "cut_db": -15.5,
        "min_cue_gap_sec": 1.25,
        "cut_spacing_sec": 3.0,
        "max_cues_per_minute": 18,
        "include_yellow_pops": False,
        "include_solo_pops": True,
        "include_secondary_money": True,
        "hero_swell_lead_in": False,
    },
    "punchy": {
        "id": "punchy",
        "label_ko": "타격감 강조형",
        "badge_ko": "고밀도 몰입 · 분당 ~28개 · -13.5dB + 차오름 빌드업",
        "desc_ko": "큰 임팩트·매출 직전 역재생 차오름(swell) 빌드업을 자동 추가하고 빠른 컷·노란 강조어까지 묵직하게 타격합니다.",
        "default_sfx_db": -13.5,
        "min_sfx_db": -16.5,
        "max_sfx_db": -12.0,
        "hook_db": -12.0,
        "accent_db": -12.5,
        "cut_db": -14.2,
        "min_cue_gap_sec": 0.55,
        "cut_spacing_sec": 1.75,
        "max_cues_per_minute": 28,
        "include_yellow_pops": True,
        "include_solo_pops": True,
        "include_secondary_money": True,
        "hero_swell_lead_in": True,
    },
}


def normalize_style_preset(preset: str | None) -> str:
    p = (preset or "balanced").strip().lower()
    aliases = {
        "깔끔": "clean",
        "깔끔형": "clean",
        "minimal": "clean",
        "standard": "balanced",
        "표준": "balanced",
        "표준형": "balanced",
        "해외쇼쇼": "balanced",
        "강조": "punchy",
        "타격감": "punchy",
        "타격감강조형": "punchy",
        "heavy": "punchy",
        "impact": "punchy",
    }
    p = aliases.get(p, p)
    return p if p in SFX_STYLE_PRESETS else "balanced"


def get_style_preset_spec(preset: str | None) -> Dict[str, Any]:
    return copy.deepcopy(SFX_STYLE_PRESETS[normalize_style_preset(preset)])


def load_favorite_stems(favorites_path: Path | None) -> Set[str]:
    """Return lowercased stem names marked as ★ favorites in assets/sfx_favorites.json."""
    if not favorites_path or not favorites_path.is_file():
        return set()
    try:
        raw = json.loads(favorites_path.read_text(encoding="utf-8"))
        items = raw.get("items", raw if isinstance(raw, list) else [])
        out: Set[str] = set()
        for x in items:
            s = str(x or "").split("/")[-1].strip()
            if s:
                out.add(Path(s).stem.lower())
                out.add(s.lower())
        return out
    except Exception:
        return set()


def _parse_bool(val: str | bool | None, default: bool = False) -> bool:
    if isinstance(val, bool):
        return val
    if val is None or str(val).strip() == "":
        return default
    return str(val).strip().lower() in {"1", "true", "yes", "on", "y"}


def _load_dotenv_if_present(env_path: Path | None = None) -> None:
    candidates = [env_path] if env_path else [Path.cwd() / ".env", REPO_ROOT / ".env"]
    for candidate in candidates:
        if candidate and candidate.is_file():
            for raw_line in candidate.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
            break


def find_agy_cli() -> str | None:
    custom = os.getenv("AGY_CLI_PATH", "").strip()
    if custom and (Path(custom).is_file() or shutil.which(custom)):
        return custom
    return shutil.which("agy")


@dataclass
class SFXConfig:
    """Runtime configuration loaded from .env + config.json."""

    auto_sfx_enabled: bool = True
    director_backend: str = "local-free"
    style_preset: str = "balanced"
    free_tier_rpm_safe: bool = True
    local_sfx_dir: Path = field(default_factory=lambda: Path(r"C:\Users\tmd39\Desktop\효과음\효과음2869개"))
    fallback_repo_sfx_dirs: List[Path] = field(
        default_factory=lambda: [REPO_ROOT / "assets" / "sfx", REPO_ROOT / "sfx"]
    )
    voice_scores_path: Path = field(default_factory=lambda: REPO_ROOT / "assets" / "sfx_voice.json")
    catalog_path: Path = field(default_factory=lambda: REPO_ROOT / "assets" / "sfx_catalog.json")
    favorites_path: Path = field(default_factory=lambda: REPO_ROOT / "assets" / "sfx_favorites.json")
    favorite_boost: float = 0.28
    cuesheet_dir: Path = field(default_factory=lambda: REPO_ROOT / "jobs" / "_cuesheets")
    gemini_api_key: str = ""
    gemini_audio_model: str = "gemini-2.5-flash"
    gemini_video_model: str = "gemini-2.5-flash"
    gemini_audio_batch_size: int = 8
    catalog_workers: int = 6
    freesound_api_key: str = ""
    elevenlabs_api_key: str = ""
    elevenlabs_model_id: str = "eleven_text_to_sound_v3"
    fallback_order: List[str] = field(default_factory=lambda: ["freesound", "elevenlabs"])
    local_match_threshold: float = 0.50
    default_sfx_db: float = -15.0
    min_sfx_db: float = -18.0
    max_sfx_db: float = -12.0
    enable_sidechain_ducking: bool = True
    anchor_snap_window_sec: float = 0.18
    auto_sync_subtitles: bool = True
    min_cue_gap_sec: float = 1.25
    max_cues_per_minute: int = 18
    ffmpeg_bin: str = "ffmpeg"
    ffprobe_bin: str = "ffprobe"

    def with_style_preset(self, preset: str | None) -> "SFXConfig":
        """Return a shallow copy tuned to the requested 해외쇼쇼 style preset."""
        cloned = copy.copy(self)
        p_id = normalize_style_preset(preset or self.style_preset)
        spec = SFX_STYLE_PRESETS[p_id]
        cloned.style_preset = p_id
        cloned.default_sfx_db = float(spec["default_sfx_db"])
        cloned.min_sfx_db = float(spec["min_sfx_db"])
        cloned.max_sfx_db = float(spec["max_sfx_db"])
        cloned.min_cue_gap_sec = float(spec["min_cue_gap_sec"])
        cloned.max_cues_per_minute = int(spec["max_cues_per_minute"])
        return cloned

    @property
    def resolved_backend(self) -> str:
        mode = (self.director_backend or "auto").strip().lower()
        if mode in {"local-free", "offline", "local", "free"}:
            return "local-free"
        if mode in {"agy-cli", "agy"}:
            return "agy-cli" if find_agy_cli() else "local-free"
        if mode in {"gemini-api", "gemini"}:
            return "gemini-api" if self.gemini_api_key else "local-free"
        if find_agy_cli():
            return "agy-cli"
        if self.gemini_api_key:
            return "gemini-api"
        return "local-free"

    @property
    def acquisition_mode(self) -> str:
        has_fs = bool(self.freesound_api_key)
        has_el = bool(self.elevenlabs_api_key)
        if has_fs and has_el:
            return "hybrid"
        if has_fs:
            return "freesound_only"
        if has_el:
            return "elevenlabs_only"
        return "local_only"

    @property
    def auto_acquired_dir(self) -> Path:
        if self.local_sfx_dir.is_dir():
            return self.local_sfx_dir / "_auto_acquired"
        return REPO_ROOT / "assets" / "sfx_auto_acquired"

    @classmethod
    def from_env(cls, env_path: Path | None = None, repo_cfg: Dict[str, Any] | None = None) -> "SFXConfig":
        _load_dotenv_if_present(env_path)
        if repo_cfg is None and (REPO_ROOT / "config.json").is_file():
            try:
                repo_cfg = json.loads((REPO_ROOT / "config.json").read_text(encoding="utf-8"))
            except Exception:
                repo_cfg = {}
        repo_cfg = repo_cfg or {}
        auto_block = repo_cfg.get("auto_sfx") or {}
        lib_block = repo_cfg.get("sfx_library") or {}

        if "AUTO_SFX_ENABLED" in os.environ and os.environ["AUTO_SFX_ENABLED"].strip() != "":
            enabled = _parse_bool(os.environ["AUTO_SFX_ENABLED"], default=True)
        else:
            enabled = _parse_bool(auto_block.get("enabled"), default=True)

        backend = (
            os.getenv("SFX_DIRECTOR_BACKEND")
            or auto_block.get("director_backend")
            or "local-free"
        ).strip().lower()

        preset = normalize_style_preset(
            os.getenv("SFX_STYLE_PRESET")
            or auto_block.get("style_preset")
            or "balanced"
        )
        spec = SFX_STYLE_PRESETS[preset]

        default_sfx_dir = (
            os.getenv("LOCAL_SFX_DIR")
            or os.getenv("SHORTS_SFX_PACK")
            or auto_block.get("local_sfx_dir")
            or lib_block.get("dir")
            or r"C:\Users\tmd39\Desktop\효과음\효과음2869개"
        )
        cat_rel = os.getenv("SFX_CATALOG_PATH") or auto_block.get("catalog_path") or "assets/sfx_catalog.json"
        cat_path = Path(cat_rel) if Path(cat_rel).is_absolute() else (REPO_ROOT / cat_rel)

        fav_rel = os.getenv("SFX_FAVORITES_PATH") or auto_block.get("favorites_path") or "assets/sfx_favorites.json"
        fav_path = Path(fav_rel) if Path(fav_rel).is_absolute() else (REPO_ROOT / fav_rel)

        cue_rel = os.getenv("SFX_CUESHEET_DIR") or auto_block.get("cuesheet_dir") or "jobs/_cuesheets"
        cue_path = Path(cue_rel) if Path(cue_rel).is_absolute() else (REPO_ROOT / cue_rel)

        gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
        raw_order = os.getenv("SFX_FALLBACK_ORDER", auto_block.get("fallback_order", "freesound,elevenlabs"))
        if isinstance(raw_order, list):
            order = [str(p).strip().lower() for p in raw_order if str(p).strip()]
        else:
            order = [p.strip().lower() for p in str(raw_order).split(",") if p.strip()]

        min_db = float(os.getenv("SFX_MIN_DB", spec["min_sfx_db"]))
        max_db = float(os.getenv("SFX_MAX_DB", spec["max_sfx_db"]))
        default_db = float(os.getenv("SFX_DEFAULT_DB", spec["default_sfx_db"]))
        min_gap = float(os.getenv("SFX_MIN_CUE_GAP_SEC", spec["min_cue_gap_sec"]))
        max_cpm = int(os.getenv("SFX_MAX_CUES_PER_MIN", spec["max_cues_per_minute"]))

        return cls(
            auto_sfx_enabled=enabled,
            director_backend=backend,
            style_preset=preset,
            free_tier_rpm_safe=_parse_bool(os.getenv("SFX_FREE_TIER_RPM_SAFE"), default=bool(auto_block.get("free_tier_rpm_safe", True))),
            local_sfx_dir=Path(default_sfx_dir),
            catalog_path=cat_path,
            favorites_path=fav_path,
            cuesheet_dir=cue_path,
            gemini_api_key=gemini_key,
            gemini_audio_model=os.getenv("GEMINI_AUDIO_MODEL", auto_block.get("gemini_audio_model", "gemini-2.5-flash")),
            gemini_video_model=os.getenv("GEMINI_VIDEO_MODEL", auto_block.get("gemini_video_model", "gemini-2.5-flash")),
            gemini_audio_batch_size=max(1, min(12, int(os.getenv("GEMINI_AUDIO_BATCH_SIZE", "8")))),
            catalog_workers=max(1, min(16, int(os.getenv("SFX_CATALOG_WORKERS", "6")))),
            freesound_api_key=os.getenv("FREESOUND_API_KEY", "").strip(),
            elevenlabs_api_key=os.getenv("ELEVENLABS_API_KEY", "").strip(),
            elevenlabs_model_id=os.getenv("ELEVENLABS_SFX_MODEL", "eleven_text_to_sound_v3").strip(),
            fallback_order=order,
            local_match_threshold=float(os.getenv("SFX_LOCAL_MATCH_THRESHOLD", auto_block.get("local_match_threshold", 0.50))),
            default_sfx_db=max(min_db, min(max_db, default_db)),
            min_sfx_db=min_db,
            max_sfx_db=max_db,
            enable_sidechain_ducking=_parse_bool(os.getenv("SFX_ENABLE_DUCKING"), default=bool(auto_block.get("ducking", True))),
            anchor_snap_window_sec=float(os.getenv("SFX_ANCHOR_SNAP_SEC", "0.18")),
            auto_sync_subtitles=_parse_bool(os.getenv("AUTO_SYNC_SUBTITLES"), default=True),
            min_cue_gap_sec=min_gap,
            max_cues_per_minute=max_cpm,
            ffmpeg_bin=os.getenv("FFMPEG_BIN", "ffmpeg"),
            ffprobe_bin=os.getenv("FFPROBE_BIN", "ffprobe"),
        )


def is_auto_sfx_enabled(repo_cfg: Dict[str, Any] | None = None) -> bool:
    return SFXConfig.from_env(repo_cfg=repo_cfg).auto_sfx_enabled
