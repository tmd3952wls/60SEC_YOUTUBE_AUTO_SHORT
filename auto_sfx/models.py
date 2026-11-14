"""Data models unified with 60SEC_YOUTUBE_AUTO_SHORT EDL & CapCut categories."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List


# Unified 13 categories matching shorts/edl.py, shorts/sfxlib.py, shorts/sfx_level.py, and editor/
STANDARD_SFX_CATEGORIES = [
    "whoosh",     # 장면 전환, 모션블러 슬라이드, 빠른 줌인/아웃
    "pop",        # 빨간 원(⭕), 자막/아이콘 톡 등장, 가벼운 전환
    "ding",       # 핵심 수치·원리·포인트 공개 (띵, 띠링, 글로켄슈필)
    "cash",       # 매출·투자금·원화 금액 + 지폐 아이콘(assets/money_icon.png) 카칭
    "impact",     # 초반 3초 강렬한 후킹 한 방, 결정적 반전 쿵(boom)
    "surprise",   # 놀람·충격·정색·색 번쩍임(flash) 리액션
    "question",   # 의문·황당·어이없음(띠용, 물음표, 예능 코믹)
    "success",    # 투자 계약 성사, 품절 대박, 긍정 결말
    "fail",       # 전원 거절(모두 아웃), 생산 중단, 오답/실패
    "tension",    # 투자 조건 제시 직전 긴장감, 시계 초침, 심장박동
    "swell",      # 큰 임팩트 직전 짧게 차오르는 역재생 심벌/라이저(riser)
    "caption",    # 텍스트 나열, 타자기, 핑거스냅 강조
    "camera",     # 증거 사진, 바이럴 캡처 화면 찰칵
]

CATEGORY_ALIASES = {
    "boom": "impact",
    "hit_boom": "impact",
    "pop_click": "pop",
    "ding_chime": "ding",
    "cash_money": "cash",
    "riser_build": "swell",
    "shock_buzz": "surprise",
    "comedy_cartoon": "question",
    "camera_shutter": "camera",
    "typing_paper": "caption",
    "ambient_drone": "tension",
    "other": "pop",
}


def normalize_category(cat: str) -> str:
    base = str(cat or "pop").split("/", 1)[0].strip().lower()
    base = CATEGORY_ALIASES.get(base, base)
    return base if base in STANDARD_SFX_CATEGORIES else "pop"


@dataclass
class SFXCatalogEntry:
    """Metadata for a single indexed SFX audio file in assets/sfx_catalog.json."""

    sfx_id: str
    file_name: str
    relative_path: str
    absolute_path: str
    fingerprint: str
    file_size_bytes: int
    mtime_ns: int
    duration_sec: float
    lead_silence_sec: float
    peak_offset_sec: float
    peak_dbfs: float
    rms_dbfs: float
    category: str
    sub_type: str
    has_human_voice: bool = False
    moods: List[str] = field(default_factory=list)
    intensity: int = 3
    description_ko: str = ""
    search_tags_en: List[str] = field(default_factory=list)
    recommended_situations: List[str] = field(default_factory=list)
    source: str = "local"  # "local" | "repo_builtin" | "freesound" | "elevenlabs"
    license_info: str = "local_asset"
    analyzed_by: str = "gemini_multimodal"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SFXCatalogEntry":
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        filtered.setdefault("lead_silence_sec", 0.0)
        filtered.setdefault("has_human_voice", False)
        filtered["category"] = normalize_category(filtered.get("category", "pop"))
        return cls(**filtered)


@dataclass
class SFXCue:
    """Single timestamped SFX direction item produced by watching the draft Short."""

    cue_id: str
    timestamp: str              # e.g. "00:01.35"
    timestamp_sec: float        # Frame/subtitle-snapped timestamp in seconds
    trigger_type: str           # "hook_0_3s" | "scene_cut" | "caption_pop" | "money_stat" | "mood_shift" | "clip_reaction" | "circle_mark"
    sfx_category: str           # One of STANDARD_SFX_CATEGORIES
    desired_sfx_query_en: str   # English query/prompt for local search + Freesound/ElevenLabs
    desired_mood: str
    intensity: int = 3
    target_db: float = -15.0    # Target level in dB (-18.0 to -12.0)
    duck_under_speech: bool = True
    max_duration_sec: float = 1.8
    pinned_name: str = ""       # Optional pinned file name from EDL ("pop/카툰 팝")
    anchor_source: str = "gemini_vision"
    matched_subtitle_text: str = ""
    director_reason_ko: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SFXCue":
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        filtered["sfx_category"] = normalize_category(filtered.get("sfx_category", "pop"))
        return cls(**filtered)


@dataclass
class SFXCuesheet:
    """Complete cuesheet output for a draft Short video."""

    video_path: str
    video_duration_sec: float
    fps: float
    overall_mood: str
    summary_ko: str
    cues: List[SFXCue] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "video_path": self.video_path,
            "video_duration_sec": round(self.video_duration_sec, 3),
            "fps": round(self.fps, 3),
            "overall_mood": self.overall_mood,
            "summary_ko": self.summary_ko,
            "cues": [c.to_dict() for c in self.cues],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SFXCuesheet":
        cues = [SFXCue.from_dict(c) for c in data.get("cues", [])]
        return cls(
            video_path=data.get("video_path", ""),
            video_duration_sec=float(data.get("video_duration_sec", 60.0)),
            fps=float(data.get("fps", 30.0)),
            overall_mood=data.get("overall_mood", ""),
            summary_ko=data.get("summary_ko", ""),
            cues=cues,
        )


@dataclass
class ResolvedSFXCue:
    """A cue paired with a concrete audio file and exact FFmpeg / CapCut timing & gain parameters."""

    cue: SFXCue
    sfx: SFXCatalogEntry
    match_score: float
    resolution_method: str      # "local_catalog" | "freesound_api" | "elevenlabs_api" | "local_fallback" | "repo_builtin"
    trim_start_sec: float
    insert_delay_ms: int
    effective_gain_db: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cue": self.cue.to_dict(),
            "sfx": self.sfx.to_dict(),
            "match_score": round(self.match_score, 3),
            "resolution_method": self.resolution_method,
            "trim_start_sec": round(self.trim_start_sec, 4),
            "insert_delay_ms": self.insert_delay_ms,
            "effective_gain_db": round(self.effective_gain_db, 2),
        }

    def to_capcut_export_dict(self, master_db: float = 0.0) -> Dict[str, Any]:
        """Return exact dict schema expected by shorts/edl.py export.json & shorts/capcut.py.

        shorts/capcut.py multiplies segment volume by `master` (10 ** (master_db / 20)),
        so subtracting `master_db` here keeps CapCut track gain 100% identical to effective_gain_db.
        """
        return {
            "t": round(self.insert_delay_ms / 1000.0, 4),
            "cat": self.cue.sfx_category,
            "name": Path(self.sfx.file_name).stem,
            "file": self.sfx.absolute_path,
            "lead": round(self.trim_start_sec, 4),
            "gain_db": round(self.effective_gain_db - float(master_db), 2),
            "max_dur": round(self.cue.max_duration_sec, 3),
        }
