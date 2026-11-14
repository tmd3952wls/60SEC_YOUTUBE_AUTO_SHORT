"""Local SFX Folder Listener & Incremental Cataloger (Requirement 2).

Optimized for C:\\Users\\tmd39\\Desktop\\효과음\\효과음2869개 (2,869+ files):
- Parallel FFmpeg 16kHz PCM decoding for exact duration_sec, lead_silence_sec, peak_offset_sec, peak_dbfs, rms_dbfs.
- Reuses existing assets/sfx_voice.json human-voice scores if available + Gemini Multimodal human-voice detection
  so vocal clips ('와우', 'What', laughter) never clash with Korean TTS or Shark Tank dialogue.
- 8-clip batched Gemini Multimodal Audio listening + incremental SHA1 fingerprinting (only new files analyzed).
- Automatic fallback indexing of repo-bundled assets/sfx/*.wav & sfx/*.mp3 if LOCAL_SFX_DIR is absent on another PC.
"""

from __future__ import annotations

import array
import concurrent.futures
import hashlib
import json
import logging
import math
import mimetypes
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from .config import SFXConfig
from .models import STANDARD_SFX_CATEGORIES, SFXCatalogEntry, normalize_category

logger = logging.getLogger("auto_sfx.cataloger")

SUPPORTED_AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac"}
MIME_MAP = {
    ".mp3": "audio/mp3",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
}

VOICE_NAME_PAT = re.compile(
    r"와우|와$|웃음|laugh|wow|what|헉|허얽|뜨헉|허엉|우와|비명|박수|환호|음성|목소리|예~|yeah|oh\s*no|no\s*no",
    re.I,
)
SYNTH_NON_VOCAL_STEMS = {"002_뿅", "뿅"}


def compute_file_fingerprint(path: Path) -> Tuple[str, int, int]:
    stat = path.stat()
    hasher = hashlib.sha1()
    hasher.update(str(stat.st_size).encode("utf-8"))
    with path.open("rb") as f:
        hasher.update(f.read(65536))
        if stat.st_size > 65536:
            f.seek(max(0, stat.st_size - 65536))
            hasher.update(f.read(65536))
    return hasher.hexdigest()[:16], stat.st_size, stat.st_mtime_ns


def analyze_audio_signal_ffmpeg(path: Path, ffmpeg_bin: str = "ffmpeg") -> Dict[str, float]:
    """Measure exact duration_sec, lead_silence_sec, peak_offset_sec (2ms/10ms transient), peak_dbfs, and rms_dbfs."""
    cmd = [
        ffmpeg_bin,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(path),
        "-f",
        "s16le",
        "-ac",
        "1",
        "-ar",
        "16000",
        "pipe:1",
    ]
    proc = subprocess.run(cmd, capture_output=True, check=False, timeout=30)
    if proc.returncode != 0 or not proc.stdout:
        return {"duration_sec": 0.8, "lead_silence_sec": 0.0, "peak_offset_sec": 0.04, "peak_dbfs": -6.0, "rms_dbfs": -18.0}

    sr = 16000
    raw = proc.stdout
    samples = array.array("h")
    samples.frombytes(raw[: len(raw) - (len(raw) % 2)])
    total = len(samples)
    if total == 0:
        return {"duration_sec": 0.5, "lead_silence_sec": 0.0, "peak_offset_sec": 0.0, "peak_dbfs": -60.0, "rms_dbfs": -60.0}

    duration_sec = total / sr
    win = 160  # 10ms window
    max_abs = 1
    best_win_sq = 0.0
    best_win_idx = 0
    sum_sq_all = 0.0
    win_dbs: List[float] = []

    for i in range(0, total, win):
        chunk = samples[i : i + win]
        if not chunk:
            break
        csq = 0.0
        for s in chunk:
            a = abs(s)
            if a > max_abs:
                max_abs = a
            csq += s * s
        sum_sq_all += csq
        msq = csq / len(chunk)
        if msq > best_win_sq:
            best_win_sq = msq
            best_win_idx = i + (len(chunk) // 2)
        win_dbs.append(20.0 * math.log10(max(math.sqrt(msq), 1.0) / 32768.0))

    peak_dbfs = 20.0 * math.log10(max(max_abs, 1) / 32768.0)
    rms_dbfs = 20.0 * math.log10(max(math.sqrt(sum_sq_all / total), 1.0) / 32768.0)

    # Detect leading silence threshold (peak_dbfs - 32dB, floored at -48dBFS)
    onset_thr = max(-48.0, peak_dbfs - 32.0)
    lead_idx = 0
    for idx, db in enumerate(win_dbs):
        if db >= onset_thr:
            lead_idx = idx
            break
    lead_silence_sec = min(duration_sec, lead_idx * 0.01)
    peak_offset_sec = min(duration_sec, best_win_idx / sr)

    return {
        "duration_sec": round(duration_sec, 4),
        "lead_silence_sec": round(lead_silence_sec, 4),
        "peak_offset_sec": round(peak_offset_sec, 4),
        "peak_dbfs": round(peak_dbfs, 2),
        "rms_dbfs": round(rms_dbfs, 2),
    }


def _heuristic_metadata_from_path(path: Path, rel_path: str, acoustic: Dict[str, float]) -> Dict[str, Any]:
    """Classifier aligned with shorts/sfxlib.py Korean onomatopoeia + English SFX patterns."""
    clean_stem = re.sub(r"^\d+_", "", path.stem)
    haystack = f"{rel_path} {clean_stem}".lower()
    tokens = [t for t in re.split(r"[\s_\-\./\\\(\)\[\]]+", haystack) if t]

    patterns = [
        ("cash", r"cash|register|chaching|cha-ching|캐셔|철컥띵|금전등록|코인|coin|돈"),
        ("whoosh", r"휘익|휙|쉭|스우쉬|whoosh|swoosh|swish|화면전환|휘리릭|훅|후욱|쉬이익|슉|스르륵|샤스륵|swipe"),
        ("pop", r"뿅|팝|뽀옹|뾰옥|뽀욕|poink|뾰잉|띡|버튼|클릭|삡|똥|물방울|바운스|pop|bubble|click"),
        ("ding", r"띵|띠링|딩|딩동|정답|ting|correct|띠룽|또잉|티딩|마법봉|뾰로롱|샤랄라|반짝|bell|chime"),
        ("impact", r"쿵|두둥탁|큰북|슉쿵|쿠웅|푸우쿵|퉁우우|텅|폭발|펑|boom|impact|hit|slam|sub"),
        ("swell", r"riser|reverse|swell|라이저|차오르|빌드업|상승"),
        ("surprise", r"놀람|뜨헉|허얽|헉|shock|깜짝|전자음|반전|glitch|scratch"),
        ("question", r"물음표|띠용|띠동|띠요용|이상할때|띠우웅|미-밋|어이없|boing|cartoon"),
        ("success", r"tada|짜잔|타랴|빰빠|레벨업|축복|good|unlocked|celebration|성공|환호"),
        ("fail", r"오답|실패|wrong|wah|망함|좌절|허무|게임 오버|fail|삐삑|삐이"),
        ("tension", r"심장|째깍|drum roll|미스테리|긴장|suspense|tick|clock"),
        ("caption", r"캡션|타자기|type writer|핑거스냅|핑거 스냅|타탁|타닥"),
        ("camera", r"찰칵|카메라|셔터|써터|shutter|snap"),
    ]
    category = "pop"
    for cat, pat in patterns:
        if re.search(pat, haystack, re.I):
            category = cat
            break
    else:
        if acoustic["duration_sec"] >= 0.55:
            category = "whoosh"

    has_voice = bool(VOICE_NAME_PAT.search(clean_stem))
    intensity = 4 if acoustic["peak_dbfs"] > -4.0 else (3 if acoustic["peak_dbfs"] > -12.0 else 2)
    return {
        "category": category,
        "sub_type": clean_stem[:28] or category,
        "has_human_voice": has_voice,
        "moods": ["punchy" if acoustic["duration_sec"] < 0.9 else "dramatic"],
        "intensity": intensity,
        "description_ko": f"{clean_stem} ({acoustic['duration_sec']:.2f}초, 타격피크 {acoustic['peak_offset_sec']:.2f}초)",
        "search_tags_en": [category] + [t for t in tokens if t.isascii()][:6],
        "recommended_situations": [category],
        "analyzed_by": "acoustic_filename_heuristic",
    }


def analyze_sfx_batch_with_gemini(
    batch_items: List[Tuple[Path, str, Dict[str, float]]],
    config: SFXConfig,
) -> List[Dict[str, Any]]:
    """Listen to up to 8 short SFX clips in a single Gemini Multimodal call."""
    if not config.gemini_api_key:
        return [_heuristic_metadata_from_path(p, rel, ac) for p, rel, ac in batch_items]

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=config.gemini_api_key)
    contents: List[Any] = []
    uploaded_refs: List[Any] = []

    item_schema = {
        "type": "OBJECT",
        "properties": {
            "clip_index": {"type": "INTEGER"},
            "category": {"type": "STRING", "enum": STANDARD_SFX_CATEGORIES},
            "sub_type": {"type": "STRING"},
            "has_human_voice": {
                "type": "BOOLEAN",
                "description": "True if the sound contains human vocalizations (e.g., Wow, What, laughter, gasps, speech).",
            },
            "moods": {"type": "ARRAY", "items": {"type": "STRING"}},
            "intensity": {"type": "INTEGER"},
            "description_ko": {"type": "STRING"},
            "search_tags_en": {"type": "ARRAY", "items": {"type": "STRING"}},
            "recommended_situations": {"type": "ARRAY", "items": {"type": "STRING"}},
        },
        "required": [
            "clip_index",
            "category",
            "sub_type",
            "has_human_voice",
            "moods",
            "intensity",
            "description_ko",
            "search_tags_en",
            "recommended_situations",
        ],
    }

    try:
        for idx, (path, rel_path, acoustic) in enumerate(batch_items):
            mime_type = MIME_MAP.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "audio/mpeg"
            raw_bytes = path.read_bytes()
            contents.append(
                f"[Clip #{idx}] 파일: '{rel_path}' (길이 {acoustic['duration_sec']:.3f}s, 파형피크 {acoustic['peak_offset_sec']:.3f}s)"
            )
            if len(raw_bytes) <= 4 * 1024 * 1024:
                contents.append(types.Part.from_bytes(data=raw_bytes, mime_type=mime_type))
            else:
                up = client.files.upload(file=str(path), config=types.UploadFileConfig(mime_type=mime_type))
                while up.state and up.state.name == "PROCESSING":
                    time.sleep(1.0)
                    up = client.files.get(name=up.name)
                uploaded_refs.append(up)
                contents.append(up)

        contents.append(
            f"위 {len(batch_items)}개 효과음을 직접 듣고 60초 쇼츠(해외쇼쇼/샤크탱크 요약 스타일) 편집용 메타데이터를 분류하세요.\n"
            "- 매출/돈/캐셔/코인 소리는 'cash', 화면전환 바람소리는 'whoosh', 빨간원/자막 톡 등장은 'pop', "
            "글로켄슈필/종소리 강조는 'ding', 묵직한 쿵 한 방은 'impact', 역재생 차오름은 'swell', "
            "사람 감탄사(와우/웃음/헉/What)가 섞여 내레이션과 겹치면 방해되는 소리는 반드시 has_human_voice=true로 표시하세요."
        )

        for attempt in range(3):
            try:
                resp = client.models.generate_content(
                    model=config.gemini_audio_model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema={"type": "OBJECT", "properties": {"results": {"type": "ARRAY", "items": item_schema}}, "required": ["results"]},
                        temperature=0.2,
                    ),
                )
                by_idx = {int(it["clip_index"]): it for it in json.loads(resp.text).get("results", []) if "clip_index" in it}
                out: List[Dict[str, Any]] = []
                for idx, (p, rel, ac) in enumerate(batch_items):
                    if idx in by_idx:
                        m = by_idx[idx]
                        m["analyzed_by"] = f"gemini:{config.gemini_audio_model}"
                        out.append(m)
                    else:
                        out.append(_heuristic_metadata_from_path(p, rel, ac))
                return out
            except Exception as exc:
                if attempt == 2:
                    logger.warning("Gemini batch audio fallback: %s", exc)
                time.sleep(2.0 * (attempt + 1))
        return [_heuristic_metadata_from_path(p, rel, ac) for p, rel, ac in batch_items]
    finally:
        for up in uploaded_refs:
            try:
                client.files.delete(name=up.name)
            except Exception:
                pass


class SFXCatalogManager:
    """Manages incremental scanning, batched Gemini audio indexing, and assets/sfx_catalog.json."""

    def __init__(self, config: SFXConfig):
        self.config = config
        self.entries_by_rel_path: Dict[str, SFXCatalogEntry] = {}
        self.voice_scores_by_stem: Dict[str, float] = self._load_legacy_voice_scores()
        self.load()

    def _load_legacy_voice_scores(self) -> Dict[str, float]:
        if not self.config.voice_scores_path.is_file():
            return {}
        try:
            raw = json.loads(self.config.voice_scores_path.read_text(encoding="utf-8"))
            return {Path(k.replace("\\", "/")).name: float(v) for k, v in raw.items()}
        except Exception:
            return {}

    def load(self) -> List[SFXCatalogEntry]:
        if not self.config.catalog_path.is_file():
            self.entries_by_rel_path = {}
            return []
        raw = json.loads(self.config.catalog_path.read_text(encoding="utf-8"))
        items = raw.get("items", raw if isinstance(raw, list) else [])
        self.entries_by_rel_path = {}
        for item in items:
            entry = SFXCatalogEntry.from_dict(item)
            self.entries_by_rel_path[entry.relative_path] = entry
        return list(self.entries_by_rel_path.values())

    def save(self) -> None:
        self.config.catalog_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": "2.0",
            "local_sfx_dir": str(self.config.local_sfx_dir),
            "total_count": len(self.entries_by_rel_path),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "items": [e.to_dict() for e in sorted(self.entries_by_rel_path.values(), key=lambda x: x.relative_path)],
        }
        self.config.catalog_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def iter_audio_files(self, root_dir: Path) -> Iterable[Path]:
        if not root_dir.is_dir():
            return []
        return sorted(p for p in root_dir.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_AUDIO_EXTS)

    def _build_entry(
        self,
        audio_path: Path,
        rel_path: str,
        fingerprint: str,
        size_bytes: int,
        mtime_ns: int,
        acoustic: Dict[str, float],
        semantic: Dict[str, Any],
        source: str = "local",
        license_info: str = "local_asset",
        extra_tags: List[str] | None = None,
    ) -> SFXCatalogEntry:
        tags = list(dict.fromkeys((semantic.get("search_tags_en") or []) + (extra_tags or [])))
        sfx_id = f"sfx_{hashlib.sha1(rel_path.encode('utf-8')).hexdigest()[:10]}"
        legacy_v = self.voice_scores_by_stem.get(audio_path.name, 0.0)
        stem_clean = re.sub(r"^\d+_", "", audio_path.stem)
        is_synth_safe = audio_path.stem in SYNTH_NON_VOCAL_STEMS or stem_clean in SYNTH_NON_VOCAL_STEMS
        has_voice = False if is_synth_safe else (bool(semantic.get("has_human_voice", False)) or (legacy_v >= 0.5))

        return SFXCatalogEntry(
            sfx_id=sfx_id,
            file_name=audio_path.name,
            relative_path=rel_path,
            absolute_path=str(audio_path.resolve()),
            fingerprint=fingerprint,
            file_size_bytes=size_bytes,
            mtime_ns=mtime_ns,
            duration_sec=acoustic["duration_sec"],
            lead_silence_sec=acoustic["lead_silence_sec"],
            peak_offset_sec=acoustic["peak_offset_sec"],
            peak_dbfs=acoustic["peak_dbfs"],
            rms_dbfs=acoustic["rms_dbfs"],
            category=normalize_category(semantic.get("category", "pop")),
            sub_type=semantic.get("sub_type", "generic"),
            has_human_voice=has_voice,
            moods=semantic.get("moods", []),
            intensity=max(1, min(5, int(semantic.get("intensity", 3)))),
            description_ko=semantic.get("description_ko", ""),
            search_tags_en=tags,
            recommended_situations=semantic.get("recommended_situations", []),
            source=source,
            license_info=license_info,
            analyzed_by=semantic.get("analyzed_by", "gemini"),
        )

    def index_single_file(
        self,
        audio_path: Path,
        source: str = "local",
        license_info: str = "local_asset",
        extra_tags: List[str] | None = None,
    ) -> SFXCatalogEntry:
        root = self.config.local_sfx_dir
        try:
            rel_path = audio_path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            rel_path = f"_external/{audio_path.name}"

        fp, sz, mt = compute_file_fingerprint(audio_path)
        acoustic = analyze_audio_signal_ffmpeg(audio_path, ffmpeg_bin=self.config.ffmpeg_bin)
        semantic = analyze_sfx_batch_with_gemini([(audio_path, rel_path, acoustic)], self.config)[0]
        entry = self._build_entry(audio_path, rel_path, fp, sz, mt, acoustic, semantic, source, license_info, extra_tags)
        self.entries_by_rel_path[rel_path] = entry
        return entry

    def sync_incremental(
        self,
        prune_missing: bool = True,
        checkpoint_every: int = 24,
        max_new_files: int | None = None,
    ) -> Dict[str, int]:
        """Incrementally index LOCAL_SFX_DIR (2,869 files), plus repo built-in assets/sfx fallback if needed."""
        scan_roots: List[Tuple[Path, str, str]] = []
        if self.config.local_sfx_dir.is_dir():
            scan_roots.append((self.config.local_sfx_dir, "", "local"))
        # Always include repo built-in fallback SFX (9 tiny files in assets/sfx & sfx/) so another PC never breaks
        for builtin_dir in self.config.fallback_repo_sfx_dirs:
            if builtin_dir.is_dir() and builtin_dir.resolve() != self.config.local_sfx_dir.resolve():
                scan_roots.append((builtin_dir, f"_repo_{builtin_dir.name}/", "repo_builtin"))

        discovered_rel_paths = set()
        pending_files: List[Tuple[Path, str, str, int, int, str]] = []
        skipped_cached = 0

        for root, prefix, default_src in scan_roots:
            for audio_path in self.iter_audio_files(root):
                sub_rel = audio_path.resolve().relative_to(root.resolve()).as_posix()
                rel_path = f"{prefix}{sub_rel}"
                discovered_rel_paths.add(rel_path)

                fp, sz, mt = compute_file_fingerprint(audio_path)
                existing = self.entries_by_rel_path.get(rel_path)
                if existing and existing.fingerprint == fp and existing.file_size_bytes == sz:
                    existing.absolute_path = str(audio_path.resolve())
                    skipped_cached += 1
                    continue

                if max_new_files is not None and len(pending_files) >= max_new_files:
                    continue
                src_tag = default_src
                if "_auto_acquired/freesound_" in rel_path:
                    src_tag = "freesound"
                elif "_auto_acquired/elevenlabs_" in rel_path:
                    src_tag = "elevenlabs"
                pending_files.append((audio_path, rel_path, fp, sz, mt, src_tag))

        added_or_updated = 0
        if pending_files:
            acoustics_map: Dict[str, Dict[str, float]] = {}
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.config.catalog_workers) as pool:
                fut_map = {
                    pool.submit(analyze_audio_signal_ffmpeg, it[0], self.config.ffmpeg_bin): it[1]
                    for it in pending_files
                }
                for fut in concurrent.futures.as_completed(fut_map):
                    acoustics_map[fut_map[fut]] = fut.result()

            batch_sz = self.config.gemini_audio_batch_size
            for start_idx in range(0, len(pending_files), batch_sz):
                chunk = pending_files[start_idx : start_idx + batch_sz]
                semantics = analyze_sfx_batch_with_gemini(
                    [(p, rel, acoustics_map[rel]) for p, rel, _, _, _, _ in chunk],
                    self.config,
                )
                for (p, rel, fp, sz, mt, src_tag), sem in zip(chunk, semantics):
                    self.entries_by_rel_path[rel] = self._build_entry(
                        p, rel, fp, sz, mt, acoustics_map[rel], sem, source=src_tag
                    )
                    added_or_updated += 1
                if added_or_updated % checkpoint_every < batch_sz:
                    self.save()

        pruned = 0
        if prune_missing and self.config.local_sfx_dir.is_dir():
            stale = [k for k in self.entries_by_rel_path if k not in discovered_rel_paths]
            for k in stale:
                del self.entries_by_rel_path[k]
                pruned += 1

        if added_or_updated > 0 or pruned > 0 or not self.config.catalog_path.is_file():
            self.save()

        return {
            "total": len(self.entries_by_rel_path),
            "added_or_updated": added_or_updated,
            "skipped_cached": skipped_cached,
            "pruned": pruned,
        }
