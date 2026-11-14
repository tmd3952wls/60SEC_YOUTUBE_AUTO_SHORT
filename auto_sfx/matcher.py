"""Hybrid SFX Matcher with ★ Favorites Priority & Automatic Fallback Acquisition."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import subprocess
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import List, Optional, Set, Tuple

import numpy as np
from scipy.signal import lfilter

from .cataloger import SFXCatalogManager
from .config import REPO_ROOT, SFXConfig, load_favorite_stems
from .models import ResolvedSFXCue, SFXCatalogEntry, SFXCue, SFXCuesheet, normalize_category

logger = logging.getLogger("auto_sfx.matcher")

CATEGORY_FALLBACK_MAP = {
    "impact": "whoosh",
    "swell": "whoosh",
    "cash": "ding",
    "success": "ding",
    "tension": "ding",
    "surprise": "pop",
    "question": "pop",
    "fail": "impact",
    "caption": "pop",
    "camera": "pop",
}

VOCAL_RUNTIME_BLOCK_RE = re.compile(
    r"와우|와$|웃음|laugh|wow|what|헉|허얽|뜨헉|허엉|우와|비명|박수|환호|음성|목소리|예~|yeah|oh\s*no|no\s*no|한숨소리|아기\s*울음",
    re.I,
)
BGM_SIREN_BLOCK_RE = re.compile(r"배경|bgm|브금|전주곡|오케스트라|싸이렌|사이렌|분위기깔기|진행중", re.I)
# 레퍼런스 15편과 결이 어긋나는 이질적·자극적·게임형 효과음 런타임 차단
GOOFY_HARSH_BLOCK_RE = re.compile(
    r"뽀욕|고무장난감|깜짝\s*놀라는\s*전자음|공포\s*전자음|짜잔|폭발|펑\s*효과음|체력,능력\s*상승|goofy\s*cartoon|실패음\(트럼펫\)|군중환호",
    re.I,
)
SYNTH_NON_VOCAL_ALLOW = {"002_뿅", "뿅"}

# 사용자 지정 참고 쇼츠 15편 스펙트로그램 분해(ref15_report.json) + socks v9 검증 시그니처 팔레트
REFERENCE_15_HERO_STEMS: dict[str, set[str]] = {
    "ding": {
        "001_띵", "띵", "185_ting", "ting", "016_띠링", "띠링",
        "265_딩 다음 페이지 넘기기", "딩 다음 페이지 넘기기", "400_전화 메시지 소리3",
        "526_화면전환효과음_01", "042_마법봉", "마법봉",
    },
    "whoosh": {
        "573_whoosh(transition)", "whoosh(transition)", "190_훅", "훅",
        "003_휘익", "휘익", "009_쉭", "쉭",
        "086_후욱 -b중간1", "089_후욱 -b중간2", "100_후욱 -a짧은2",
        "punchy_whoosh_02_swish hit (13lrs)",
    },
    "swell": {
        "087_스르륵 효과음", "스르륵 효과음", "053_샤스륵 효과음", "샤스륵 효과음",
    },
    "pop": {
        "002_뿅", "뿅", "008_팝", "팝", "037_카툰 팝", "카툰 팝",
    },
    "cash": {
        "cash_register_1", "cash_register_2",
        "010_철컥띵 (캐셔)", "철컥띵 (캐셔)", "292_cash register", "cash register",
    },
    "impact": {
        "boom", "405_쿠웅_떨어지며_울리는", "085_둥(큰북소리)", "007_쿵 효과음", "쿵 효과음",
    },
    "question": {
        "015_띠동띠동(물음표)", "띠동띠동(물음표)", "144_띠용(빠른)",
    },
    "success": {
        "468_또잉(정답소리)", "또잉(정답소리)", "379_correct", "correct",
        "414_correct answer", "239_정답음_띠롱_띵동",
    },
    "surprise": {
        "042_마법봉", "마법봉", "021_놀람.발견", "255_놀람_반전",
    },
    "fail": {
        "019_삐삑 (오답 -짧은)", "삐삑 (오답 -짧은)", "boom",
    },
    "tension": {
        "0915_clock tick", "clock tick", "1106_suspense1", "1768_suspense5",
    },
    "caption": {
        "267_캡션 사운드 타탁", "캡션 사운드 타탁", "505_일반 캡션", "310_핑거 스냅(딱)",
    },
    "camera": {
        "502_카메라 플래시 셔터", "018_찰칵 (카메라)", "560_카메라 찰칵",
    },
}

# 각 카테고리 1순위 시그니처 대표 음원 (동점 시 최우선 선택)
REFERENCE_15_PRIMARY_STEMS: dict[str, set[str]] = {
    "pop": {"002_뿅", "뿅"},
    "cash": {"cash_register_1", "010_철컥띵 (캐셔)", "철컥띵 (캐셔)"},
    "whoosh": {"573_whoosh(transition)", "whoosh(transition)", "190_훅", "훅"},
    "ding": {"001_띵", "띵", "185_ting", "ting"},
    "success": {"468_또잉(정답소리)", "또잉(정답소리)"},
    "question": {"015_띠동띠동(물음표)", "띠동띠동(물음표)"},
    "swell": {"087_스르륵 효과음", "스르륵 효과음"},
    "impact": {"boom", "405_쿠웅_떨어지며_울리는"},
    "caption": {"267_캡션 사운드 타탁", "캡션 사운드 타탁"},
}

# BS.1770 K-가중 목소리 대비 들리는 상대 크기(dB) — shorts/sfx_level.py & socks/full_v9 검증 기준
VOICE_REL_OFFSET_DB: dict[str, float] = {
    "impact": -0.5,
    "cash": -1.5,
    "success": -1.5,
    "fail": -1.5,
    "ding": -2.5,
    "pop": -2.5,
    "question": -2.5,
    "surprise": -2.5,
    "camera": -3.0,
    "whoosh": -3.2,
    "caption": -4.0,
    "swell": -5.0,
    "tension": -6.5,
}

_VERIFIED_LIB_CACHE: dict[str, set[str]] | None = None


def _get_verified_library_stems() -> dict[str, set[str]]:
    global _VERIFIED_LIB_CACHE
    if _VERIFIED_LIB_CACHE is not None:
        return _VERIFIED_LIB_CACHE
    out: dict[str, set[str]] = {}
    lib_p = REPO_ROOT / "assets" / "sfx_library.json"
    clap_p = REPO_ROOT / "assets" / "sfx_clap.json"
    try:
        clap = json.loads(clap_p.read_text(encoding="utf-8")) if clap_p.is_file() else {}
        lib = json.loads(lib_p.read_text(encoding="utf-8")) if lib_p.is_file() else {}
        for cat, items in lib.items():
            if not isinstance(items, list):
                continue
            stems: set[str] = set()
            for it in items:
                fp = str(it.get("file", ""))
                if clap.get(fp, {}).get("ok", True) is False:
                    continue
                st = Path(fp).stem.lower()
                nm = str(it.get("name", "")).strip().lower()
                if st:
                    stems.add(st)
                if nm:
                    stems.add(nm)
            out[cat] = stems
    except Exception:
        out = {}
    _VERIFIED_LIB_CACHE = out
    return out


def _tokenize(text: str) -> set[str]:
    return {tok for tok in re.split(r"[^a-z0-9가-힣]+", text.lower()) if len(tok) >= 2}


def _slugify(text: str, max_len: int = 32) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return (slug[:max_len] or "sfx").strip("_")


def is_favorite_entry(entry: SFXCatalogEntry, favorite_stems: Set[str]) -> bool:
    if not favorite_stems:
        return False
    fname_lower = entry.file_name.lower()
    stem_lower = Path(entry.file_name).stem.lower()
    if fname_lower in favorite_stems or stem_lower in favorite_stems:
        return True
    # Also match stripped numeric prefix (e.g. "003_휘익_whoosh" <-> "휘익_whoosh")
    stripped = re.sub(r"^\d+[._\-\s]+", "", stem_lower)
    return bool(stripped and stripped in favorite_stems)


def score_catalog_entry(
    cue: SFXCue,
    entry: SFXCatalogEntry,
    usage_counts: Counter,
    favorite_stems: Set[str] | None = None,
    favorite_boost: float = 0.28,
) -> float:
    if not Path(entry.absolute_path).is_file():
        return 0.0

    # 1. Explicit per-cue pinned sound always wins (1.0)
    if cue.pinned_name:
        pin = cue.pinned_name.split("/", 1)[-1].strip().lower()
        pin_stem = Path(pin).stem.lower()
        entry_name = entry.file_name.lower()
        entry_stem = Path(entry.file_name).stem.lower()
        if pin and (pin == entry_name or pin == entry_stem or pin_stem == entry_stem):
            return 1.0
        if pin and pin in entry_name:
            return 0.995

    entry_stem = Path(entry.file_name).stem.lower()
    stripped_stem = re.sub(r"^\d+[._\-\s]+", "", entry_stem)

    # Block BGM/siren ambience and goofy/harsh RPG/horror files from acting as short SFX
    if BGM_SIREN_BLOCK_RE.search(stripped_stem) or GOOFY_HARSH_BLOCK_RE.search(stripped_stem):
        return 0.0

    # Never overlay human vocal SFX ("와우", laughter, "What") on top of active narration/dialogue
    is_synth_safe = entry_stem in SYNTH_NON_VOCAL_ALLOW or stripped_stem in SYNTH_NON_VOCAL_ALLOW
    has_vocal = False if is_synth_safe else (entry.has_human_voice or bool(VOCAL_RUNTIME_BLOCK_RE.search(stripped_stem)))
    if cue.duck_under_speech and has_vocal:
        return 0.0

    score = 0.0
    cat_matched = False
    hero_pool = REFERENCE_15_HERO_STEMS.get(cue.sfx_category, set())
    is_ref_hero = entry_stem in hero_pool or stripped_stem in hero_pool
    primary_pool = REFERENCE_15_PRIMARY_STEMS.get(cue.sfx_category, set())
    is_ref_primary = entry_stem in primary_pool or stripped_stem in primary_pool

    if entry.category == cue.sfx_category or is_ref_hero:
        score += 0.48
        cat_matched = True
    elif entry.category == CATEGORY_FALLBACK_MAP.get(cue.sfx_category):
        score += 0.22
        cat_matched = True

    if entry.source != "repo_builtin" or is_ref_hero:
        score += 0.06

    # 2. ★ User Favorite Priority Boost: prioritize starred sounds within matching category
    # while still respecting usage_counts diversity so multiple starred sounds rotate naturally!
    if cat_matched and favorite_stems and is_favorite_entry(entry, favorite_stems):
        score += favorite_boost

    # 3. Reference-15 Curated Palette & clap-verified library priority
    if is_ref_hero:
        score += 0.22 + (0.05 if is_ref_primary else 0.0)
    elif cat_matched:
        v_stems = _get_verified_library_stems().get(cue.sfx_category, set())
        if entry_stem in v_stems or stripped_stem in v_stems:
            score += 0.08

    cue_tokens = _tokenize(f"{cue.desired_sfx_query_en} {cue.desired_mood} {cue.director_reason_ko}")
    entry_tokens = _tokenize(
        " ".join([entry.sub_type, entry.description_ko, *entry.search_tags_en, *entry.moods, *entry.recommended_situations])
    )
    if cue_tokens and entry_tokens:
        overlap = len(cue_tokens & entry_tokens) / max(1, min(len(cue_tokens), 5))
        score += min(0.22, overlap * 0.22)

    if entry.duration_sec <= cue.max_duration_sec * 1.3:
        score += 0.12
    elif entry.duration_sec <= cue.max_duration_sec * 2.2:
        score += 0.05

    diff = abs(entry.intensity - cue.intensity)
    score += max(0.0, 0.08 - diff * 0.025)

    # Diversity penalty: avoid repeating the exact same sound file back-to-back
    used = usage_counts.get(entry.sfx_id, 0)
    if used > 0:
        score -= min(0.36, used * 0.14)

    # Cap non-pinned score at 0.98 so explicit pinned_name (0.995~1.0) always takes precedence
    return round(max(0.0, min(0.98, score)), 4)


def acquire_from_freesound(
    cue: SFXCue,
    catalog: SFXCatalogManager,
    config: SFXConfig,
) -> Optional[SFXCatalogEntry]:
    """Search Freesound APIv2 and download HQ MP3 preview into LOCAL_SFX_DIR/_auto_acquired/."""
    if not config.freesound_api_key:
        return None

    max_dur = max(0.5, min(5.0, cue.max_duration_sec * 1.4))
    params = {
        "query": cue.desired_sfx_query_en,
        "filter": f"duration:[0.08 TO {max_dur:.2f}]",
        "sort": "rating_desc",
        "fields": "id,name,tags,duration,previews,license,avg_rating,username",
        "page_size": "5",
        "token": config.freesound_api_key,
    }
    url = f"https://freesound.org/apiv2/search/?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "60SEC-Auto-SFX-Director/2.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))

        for candidate in payload.get("results") or []:
            previews = candidate.get("previews") or {}
            preview_url = previews.get("preview-hq-mp3") or previews.get("preview-lq-mp3")
            if not preview_url:
                continue

            sound_id = candidate.get("id")
            slug = _slugify(cue.desired_sfx_query_en)
            out_dir = config.auto_acquired_dir
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"freesound_{sound_id}_{slug}.mp3"

            if not out_path.is_file():
                dl_req = urllib.request.Request(preview_url, headers={"User-Agent": "60SEC-Auto-SFX-Director/2.0"})
                with urllib.request.urlopen(dl_req, timeout=25) as audio_resp:
                    out_path.write_bytes(audio_resp.read())

            license_str = f"Freesound #{sound_id} by {candidate.get('username', 'unknown')} ({candidate.get('license', '')})"
            extra_tags = list(candidate.get("tags") or [])[:6] + sorted(_tokenize(cue.desired_sfx_query_en))
            entry = catalog.index_single_file(out_path, source="freesound", license_info=license_str, extra_tags=extra_tags)
            entry.category = normalize_category(cue.sfx_category)
            catalog.save()
            logger.info("Acquired SFX via Freesound APIv2: %s", out_path.name)
            return entry
    except Exception as exc:
        logger.warning("Freesound acquisition failed for '%s': %s", cue.desired_sfx_query_en, exc)
    return None


def acquire_from_elevenlabs(
    cue: SFXCue,
    catalog: SFXCatalogManager,
    config: SFXConfig,
) -> Optional[SFXCatalogEntry]:
    """Generate bespoke SFX via ElevenLabs Sound Effects API (eleven_text_to_sound_v3) and cache locally."""
    if not config.elevenlabs_api_key:
        return None

    duration_sec = round(max(0.5, min(4.5, cue.max_duration_sec)), 1)
    prompt_text = (
        f"Clean crisp YouTube Shorts sound effect: {cue.desired_sfx_query_en}, "
        f"{cue.desired_mood} mood, single distinct non-vocal foley/UI hit, no speech, no music"
    )
    payload_bytes = json.dumps(
        {
            "text": prompt_text,
            "duration_seconds": duration_sec,
            "prompt_influence": 0.45,
            "model_id": config.elevenlabs_model_id,
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        "https://api.elevenlabs.io/v1/sound-generation",
        data=payload_bytes,
        method="POST",
        headers={
            "xi-api-key": config.elevenlabs_api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
    )
    try:
        slug = _slugify(cue.desired_sfx_query_en)
        digest = hashlib.sha1(prompt_text.encode("utf-8")).hexdigest()[:8]
        out_dir = config.auto_acquired_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"elevenlabs_{digest}_{slug}.mp3"

        if not out_path.is_file():
            with urllib.request.urlopen(req, timeout=35) as resp:
                out_path.write_bytes(resp.read())

        entry = catalog.index_single_file(
            out_path,
            source="elevenlabs",
            license_info=f"ElevenLabs {config.elevenlabs_model_id}",
            extra_tags=sorted(_tokenize(cue.desired_sfx_query_en)),
        )
        entry.category = normalize_category(cue.sfx_category)
        catalog.save()
        logger.info("Generated & cached SFX via ElevenLabs API: %s", out_path.name)
        return entry
    except Exception as exc:
        logger.warning("ElevenLabs SFX generation failed for '%s': %s", cue.desired_sfx_query_en, exc)
    return None


def compute_alignment_and_gain(
    cue: SFXCue,
    sfx: SFXCatalogEntry,
    config: SFXConfig,
) -> Tuple[float, int, float]:
    """Strip dead leading silence, align sfx.peak_offset_sec strictly to cue.timestamp_sec, and stage perceptual gain."""
    # Trim dead leading silence (keeping 15ms natural pre-attack) so atrim(max_duration_sec) never chokes chimes!
    base_trim = round(max(0.0, min(sfx.lead_silence_sec - 0.015, sfx.peak_offset_sec - 0.02)), 4)
    eff_peak = max(0.0, sfx.peak_offset_sec - base_trim)

    if cue.timestamp_sec >= eff_peak:
        trim_start_sec = base_trim
        insert_delay_ms = int(round((cue.timestamp_sec - eff_peak) * 1000.0))
    else:
        trim_start_sec = round(sfx.peak_offset_sec - cue.timestamp_sec, 4)
        insert_delay_ms = 0

    target_db = max(config.min_sfx_db, min(config.max_sfx_db, cue.target_db))
    # Perceptual crest-factor compensation: thin bell chimes (~20dB crest) get slight lift so they match dense hits
    crest_db = max(0.0, sfx.peak_dbfs - sfx.rms_dbfs)
    crest_comp = max(-1.5, min(2.8, (crest_db - 14.0) * 0.32))
    raw_gain_db = (target_db - sfx.peak_dbfs) + crest_comp
    # Prevent true-peak clipping (keep individual SFX peak <= -1.5 dBFS)
    raw_gain_db = min(raw_gain_db, -1.5 - sfx.peak_dbfs)
    effective_gain_db = round(max(-30.0, min(12.0, raw_gain_db)), 2)
    return trim_start_sec, insert_delay_ms, effective_gain_db


def resolve_cuesheet(
    cuesheet: SFXCuesheet,
    catalog: SFXCatalogManager,
    config: SFXConfig,
) -> List[ResolvedSFXCue]:
    resolved: List[ResolvedSFXCue] = []
    usage_counts: Counter = Counter()
    favorite_stems = load_favorite_stems(config.favorites_path)

    for cue in cuesheet.cues:
        entries = list(catalog.entries_by_rel_path.values())
        best_non_repo: Optional[SFXCatalogEntry] = None
        best_non_repo_score = 0.0
        best_any: Optional[SFXCatalogEntry] = None
        best_any_score = 0.0

        for entry in entries:
            sc = score_catalog_entry(
                cue,
                entry,
                usage_counts,
                favorite_stems=favorite_stems,
                favorite_boost=config.favorite_boost,
            )
            if sc > best_any_score:
                best_any_score = sc
                best_any = entry
            e_stem = Path(entry.file_name).stem.lower()
            e_stripped = re.sub(r"^\d+[._\-\s]+", "", e_stem)
            hero_pool = REFERENCE_15_HERO_STEMS.get(cue.sfx_category, set())
            if (entry.source != "repo_builtin" or e_stem in hero_pool or e_stripped in hero_pool) and sc > best_non_repo_score:
                best_non_repo_score = sc
                best_non_repo = entry

        chosen_entry: Optional[SFXCatalogEntry] = None
        chosen_score = 0.0
        method = "local_catalog"

        if best_any is not None and best_any_score >= 0.99:
            chosen_entry = best_any
            chosen_score = best_any_score
            method = "pinned_sound"
        elif best_any is not None and is_favorite_entry(best_any, favorite_stems) and best_any_score >= config.local_match_threshold:
            chosen_entry = best_any
            chosen_score = best_any_score
            method = "favorite_local"
        elif best_non_repo is not None and best_non_repo_score >= config.local_match_threshold:
            chosen_entry = best_non_repo
            chosen_score = best_non_repo_score
            method = "local_catalog"
        else:
            for provider in config.fallback_order:
                if provider == "freesound" and config.freesound_api_key:
                    acq = acquire_from_freesound(cue, catalog, config)
                    if acq is not None:
                        chosen_entry, chosen_score, method = acq, 0.90, "freesound_api"
                        break
                elif provider == "elevenlabs" and config.elevenlabs_api_key:
                    acq = acquire_from_elevenlabs(cue, catalog, config)
                    if acq is not None:
                        chosen_entry, chosen_score, method = acq, 0.92, "elevenlabs_api"
                        break

            if chosen_entry is None and best_any is not None and best_any_score > 0.0:
                chosen_entry = best_any
                chosen_score = best_any_score
                method = "repo_builtin" if best_any.source == "repo_builtin" else "local_fallback"

        if chosen_entry is None:
            continue

        usage_counts[chosen_entry.sfx_id] += 1
        trim_start, delay_ms, gain_db = compute_alignment_and_gain(cue, chosen_entry, config)
        resolved.append(
            ResolvedSFXCue(
                cue=cue,
                sfx=chosen_entry,
                match_score=chosen_score,
                resolution_method=method,
                trim_start_sec=trim_start,
                insert_delay_ms=delay_ms,
                effective_gain_db=gain_db,
            )
        )
    return resolved


def _kw_filter_48k(x: np.ndarray) -> np.ndarray:
    """BS.1770 K-weighting filter for 48kHz stereo PCM."""
    y = lfilter([1.53512485958697, -2.69169618940638, 1.19839281085285], [1.0, -1.69065929318241, 0.73248077421585], x, axis=0)
    return lfilter([1.0, -2.0, 1.0], [1.0, -1.99004745483398, 0.99007225036621], y, axis=0)


def _momentary_lufs_48k(x: np.ndarray, hop: float = 0.02) -> Tuple[np.ndarray, np.ndarray]:
    """0.4s BS.1770 momentary loudness curve at 48kHz."""
    sr = 48000
    z = (_kw_filter_48k(x) ** 2).sum(axis=1)
    w, h = int(0.4 * sr), max(1, int(hop * sr))
    if len(z) < w:
        z = np.pad(z, (0, w - len(z)))
    c = np.concatenate([[0.0], np.cumsum(z)])
    starts = np.arange(0, len(z) - w + 1, h)
    p = (c[starts + w] - c[starts]) / w
    return (starts + w / 2) / sr, -0.691 + 10.0 * np.log10(p + 1e-12)


def _integrated_lufs_48k(x: np.ndarray) -> float:
    _, m = _momentary_lufs_48k(x, hop=0.1)
    m = m[m > -70.0]
    if not len(m):
        return -70.0
    rel = 10.0 * np.log10(np.mean(10.0 ** (m / 10.0))) - 10.0
    m = m[m > rel]
    if not len(m):
        return -70.0
    return float(10.0 * np.log10(np.mean(10.0 ** (m / 10.0))))


def calibrate_resolved_cues_to_voice(
    video_path: Path,
    resolved: List[ResolvedSFXCue],
    ffmpeg_bin: str = "ffmpeg",
) -> None:
    """Calibrate each SFX's gain using BS.1770 K-weighted loudness relative to local speaker voice loudness."""
    if not resolved or not video_path.is_file():
        return
    proc = subprocess.run(
        [ffmpeg_bin, "-v", "error", "-i", str(video_path), "-ac", "2", "-ar", "48000", "-f", "f32le", "-"],
        capture_output=True,
        check=False,
        timeout=45,
    )
    if proc.returncode != 0 or len(proc.stdout) < 8 * 4800:
        return
    voice = np.frombuffer(proc.stdout, dtype=np.float32)
    voice = voice[: (len(voice) // 2) * 2].reshape(-1, 2)
    v_int = _integrated_lufs_48k(voice)
    # Leave synthetic silent test videos untouched so raw target_db tests behave deterministically
    if v_int <= -52.0:
        return

    vt, vm = _momentary_lufs_48k(voice, hop=0.02)
    sfx_pcm_cache: dict[str, np.ndarray] = {}
    for item in resolved:
        fpath = item.sfx.absolute_path
        if fpath not in sfx_pcm_cache:
            sp = subprocess.run(
                [ffmpeg_bin, "-v", "error", "-i", fpath, "-ac", "2", "-ar", "48000", "-f", "f32le", "-"],
                capture_output=True,
                check=False,
                timeout=15,
            )
            if sp.returncode != 0 or len(sp.stdout) < 16:
                continue
            arr = np.frombuffer(sp.stdout, dtype=np.float32)
            sfx_pcm_cache[fpath] = arr[: (len(arr) // 2) * 2].reshape(-1, 2)
        full_sfx = sfx_pcm_cache[fpath]
        a0 = max(0, int(round(item.trim_start_sec * 48000)))
        a1 = min(len(full_sfx), a0 + max(2400, int(round(item.cue.max_duration_sec * 48000))))
        seg = full_sfx[a0:a1]
        if len(seg) < 480:
            continue
        _, sm = _momentary_lufs_48k(seg, hop=0.01)
        s_loud = float(sm.max())
        seg_peak_db = float(20.0 * np.log10(np.max(np.abs(seg)) + 1e-9))

        t = float(item.cue.timestamp_sec)
        sel = (vt > t - 0.5) & (vt < t + 0.5) & (vm > v_int - 20.0)
        v_loc = float(np.percentile(vm[sel], 75)) if np.any(sel) else v_int

        offset = VOICE_REL_OFFSET_DB.get(item.cue.sfx_category, -3.0)
        raw_gain = (v_loc + offset) - s_loud
        max_no_clip = -1.2 - seg_peak_db
        item.effective_gain_db = round(max(-28.0, min(14.0, max_no_clip, raw_gain)), 2)
