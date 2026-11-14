"""Video-Watching & Zero-Cost Smart SFX Cuesheet Director with 해외쇼쇼 Style Presets."""

from __future__ import annotations

import json
import logging
import math
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import (
    REPO_ROOT,
    SFX_STYLE_PRESETS,
    SFXConfig,
    find_agy_cli,
    get_style_preset_spec,
    normalize_style_preset,
)
from .models import STANDARD_SFX_CATEGORIES, SFXCue, SFXCuesheet, normalize_category
from .sync_anchor import (
    SubtitleEvent,
    extract_speech_onsets_ffmpeg,
    find_companion_subtitle_file,
    parse_subtitle_file,
    snap_cue_timestamp_to_anchors,
    snap_subtitles_to_speech_onsets,
    write_srt_file,
)

logger = logging.getLogger("auto_sfx.cuesheet")

TRIGGER_TYPES = [
    "hook_0_3s",
    "scene_cut",
    "caption_pop",
    "money_stat",
    "mood_shift",
    "clip_reaction",
    "circle_mark",
]

CATEGORY_DEFAULT_QUERY = {
    "whoosh": "fast clean whoosh swipe transition",
    "pop": "crisp cartoon bubble pop click",
    "ding": "bright bell ding chime accent",
    "cash": "cash register cha ching coin ding",
    "impact": "deep punchy cinematic bass hit boom",
    "surprise": "dramatic shock sting impact",
    "question": "quirky pizzicato pluck boing question",
    "success": "positive level up chime success",
    "fail": "sad trombone buzzer fail thud",
    "tension": "suspenseful clock tick heartbeat pulse",
    "swell": "short reverse cymbal riser whoosh build",
    "caption": "subtle digital pop text click",
    "camera": "crisp camera shutter flash click",
}

SOLO_INTERJECTION_RE = re.compile(r"^(와우|맙소사|오\s?마이\s?갓|세상에|헐|대박|어머)[!?.~\s]*$")


def probe_video_metadata(video_path: Path, ffprobe_bin: str = "ffprobe") -> Dict[str, float]:
    cmd = [
        ffprobe_bin, "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=r_frame_rate,duration:format=duration",
        "-of", "json", str(video_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=20)
    if proc.returncode != 0 or not proc.stdout:
        return {"duration_sec": 60.0, "fps": 30.0}
    data = json.loads(proc.stdout)
    streams = data.get("streams") or [{}]
    fmt = data.get("format") or {}
    dur = float(streams[0].get("duration") or fmt.get("duration") or 60.0)
    rate_str = str(streams[0].get("r_frame_rate", "30/1"))
    fps = float(rate_str.split("/")[0]) / max(1.0, float(rate_str.split("/")[1])) if "/" in rate_str else float(rate_str)
    return {"duration_sec": dur, "fps": round(fps, 3)}


def format_mmss_ms(seconds: float) -> str:
    seconds = max(0.0, seconds)
    mins = int(seconds // 60)
    rem = seconds - mins * 60
    return f"{mins:02d}:{rem:05.2f}"


def parse_timestamp_to_sec(ts: str | float | int) -> float:
    if isinstance(ts, (int, float)):
        return max(0.0, float(ts))
    s = str(ts).strip()
    if ":" in s:
        parts = s.split(":")
        if len(parts) == 2:
            return max(0.0, int(parts[0]) * 60 + float(parts[1]))
        if len(parts) == 3:
            return max(0.0, int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2]))
    return max(0.0, float(s))


def detect_visual_cuts_ffmpeg(video_path: Path, ffmpeg_bin: str = "ffmpeg") -> List[float]:
    cmd = [
        ffmpeg_bin, "-hide_banner", "-i", str(video_path),
        "-vf", "select='gt(scene,0.22)',showinfo", "-an", "-f", "null", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=60)
    cuts: List[float] = []
    if proc.stderr:
        for line in proc.stderr.splitlines():
            if "pts_time:" in line:
                for token in line.split():
                    if token.startswith("pts_time:"):
                        try:
                            val = round(float(token.split(":", 1)[1]), 3)
                            if not cuts or (val - cuts[-1]) >= 0.15:
                                cuts.append(val)
                        except ValueError:
                            pass
    return cuts


def _reconstruct_marked_text(x: Dict[str, Any]) -> str:
    raw = str(x.get("text", "")).strip()
    if raw:
        return raw.replace("|", " ")
    parts: List[str] = []
    for span in (x.get("spans") or []):
        if isinstance(span, (list, tuple)) and len(span) >= 2:
            t_part, col = str(span[0]), str(span[1]).removesuffix("_s")
            if col in {"green", "red", "yellow", "cyan", "pink"} and t_part.strip():
                parts.append(f"[{col}:{t_part}]")
            else:
                parts.append(t_part)
    return "".join(parts).replace("\n", " ").strip()


def _sub_events_from_edl_sub_list(edl_sub_list: List[Dict[str, Any]]) -> List[SubtitleEvent]:
    out: List[SubtitleEvent] = []
    for idx, x in enumerate(edl_sub_list, start=1):
        raw_txt = _reconstruct_marked_text(x)
        out.append(
            SubtitleEvent(
                index=idx,
                start_sec=round(float(x["a"]), 3),
                end_sec=round(float(x["b"]), 3),
                text=raw_txt,
                solo=bool(x.get("solo", False)),
                icon=str(x.get("icon", "")),
            )
        )
    return out


def _normalize_snap_and_filter_cues(
    raw_cues: List[Dict[str, Any]],
    video_duration_sec: float,
    visual_cuts: List[float],
    subtitles: List[SubtitleEvent],
    speech_onsets: List[float],
    config: SFXConfig,
) -> List[SFXCue]:
    parsed: List[SFXCue] = []
    for idx, item in enumerate(raw_cues, start=1):
        ts_sec = item.get("timestamp_sec")
        if ts_sec is None:
            ts_sec = parse_timestamp_to_sec(item.get("timestamp", 0.0))
        ts_sec = max(0.0, min(max(0.1, video_duration_sec - 0.12), float(ts_sec)))

        trig = item.get("trigger_type", "scene_cut")
        if trig not in TRIGGER_TYPES:
            trig = "scene_cut"

        raw_cat = str(item.get("sfx_category", "pop"))
        pinned_name = ""
        if "/" in raw_cat:
            raw_cat, pinned_name = raw_cat.split("/", 1)
        cat = normalize_category(raw_cat)

        if item.get("exact_anchor"):
            snapped_sec = round(ts_sec, 3)
            anchor_src = str(item.get("anchor_source", "edl_exact"))
            matched_sub = str(item.get("matched_subtitle_text", ""))
        else:
            snapped_sec, anchor_src, matched_sub = snap_cue_timestamp_to_anchors(
                raw_ts_sec=ts_sec,
                trigger_type=trig,
                visual_cuts=visual_cuts,
                subtitles=subtitles,
                speech_onsets=speech_onsets,
                snap_window_sec=config.anchor_snap_window_sec,
            )

        target_db = float(item.get("target_db", config.default_sfx_db))
        target_db = round(max(config.min_sfx_db, min(config.max_sfx_db, target_db)), 1)

        parsed.append(
            SFXCue(
                cue_id=f"cue_{idx:02d}",
                timestamp=format_mmss_ms(snapped_sec),
                timestamp_sec=snapped_sec,
                trigger_type=trig,
                sfx_category=cat,
                desired_sfx_query_en=item.get("desired_sfx_query_en") or CATEGORY_DEFAULT_QUERY.get(cat, f"{cat} sound effect"),
                desired_mood=item.get("desired_mood", "punchy"),
                intensity=max(1, min(5, int(item.get("intensity", 3)))),
                target_db=target_db,
                duck_under_speech=bool(item.get("duck_under_speech", True)),
                max_duration_sec=float(item.get("max_duration_sec", 1.8)),
                pinned_name=pinned_name or str(item.get("pinned_name", "")),
                anchor_source=anchor_src,
                matched_subtitle_text=matched_sub or str(item.get("matched_subtitle_text", "")),
                director_reason_ko=str(item.get("director_reason_ko", "")),
            )
        )

    parsed.sort(key=lambda c: (c.timestamp_sec, -(10 if c.pinned_name else c.intensity)))

    filtered: List[SFXCue] = []
    for cue in parsed:
        if not filtered:
            filtered.append(cue)
            continue
        prev = filtered[-1]
        gap = cue.timestamp_sec - prev.timestamp_sec
        # Allow intentional riser lead-in (`swell` -> hero hit 0.25s~0.6s later) in punchy preset
        is_swell_build = prev.sfx_category == "swell" and cue.sfx_category in {"impact", "cash", "success", "fail"} and gap >= 0.22
        if gap >= config.min_cue_gap_sec or is_swell_build:
            filtered.append(cue)
        elif cue.pinned_name or cue.intensity > prev.intensity:
            filtered[-1] = cue

    max_allowed = max(2, int(math.ceil((video_duration_sec / 60.0) * config.max_cues_per_minute)))
    if len(filtered) > max_allowed:
        priority = [c for c in filtered if c.pinned_name or c.trigger_type in {"hook_0_3s", "money_stat"} or c.timestamp_sec <= 3.0]
        rest = sorted([c for c in filtered if c not in priority], key=lambda c: c.intensity, reverse=True)
        filtered = sorted(priority + rest[: max(0, max_allowed - len(priority))], key=lambda c: c.timestamp_sec)

    for idx, cue in enumerate(filtered, start=1):
        cue.cue_id = f"cue_{idx:02d}"
    return filtered


def _build_smart_local_cues(
    seed_hint_cues: List[Dict[str, Any]],
    visual_cuts: List[float],
    subtitles: List[SubtitleEvent],
    speech_onsets: List[float],
    duration_sec: float,
    preset_id: str = "balanced",
) -> List[Dict[str, Any]]:
    """Zero-cost (0원) semantic + acoustic cuesheet builder tuned to 해외쇼쇼 style presets."""
    spec = get_style_preset_spec(preset_id)
    hook_db = float(spec["hook_db"])
    accent_db = float(spec["accent_db"])
    cut_db = float(spec["cut_db"])
    cut_spacing = float(spec["cut_spacing_sec"])

    # Adjust seed hint cue dBs to match the active preset envelope
    raw_cues: List[Dict[str, Any]] = []
    for sc in seed_hint_cues:
        c = dict(sc)
        cat = normalize_category(str(c.get("sfx_category", "pop")))
        c["target_db"] = hook_db if cat == "impact" else (accent_db if cat in {"cash", "success", "fail"} else float(spec["default_sfx_db"]))
        raw_cues.append(c)

    # EDL에 장면별 맞춤 연출 힌트가 충분히 지정된 경우(4개 이상), 불필요한 휴리스틱 남발 없이 EDL 정밀 큐를 그대로 존중
    if len(seed_hint_cues) >= 4:
        for sub in subtitles:
            if sub.icon == "money" and not any(
                normalize_category(str(c.get("sfx_category", ""))) == "cash" and abs(float(c["timestamp_sec"]) - sub.start_sec) <= 0.25
                for c in raw_cues
            ):
                clean_m = re.sub(r"\[(\w+:)?|\]", "", sub.text).strip()
                raw_cues.append(
                    {
                        "timestamp_sec": sub.start_sec,
                        "trigger_type": "money_stat",
                        "sfx_category": "cash",
                        "desired_sfx_query_en": CATEGORY_DEFAULT_QUERY["cash"],
                        "desired_mood": "exciting",
                        "intensity": 5,
                        "target_db": accent_db,
                        "duck_under_speech": True,
                        "max_duration_sec": 1.6,
                        "exact_anchor": True,
                        "anchor_source": "subtitle_onset",
                        "matched_subtitle_text": clean_m,
                        "director_reason_ko": f"지폐 아이콘 핵심 금액('{clean_m[:18]}') 캐셔음 동기화",
                    }
                )
        return raw_cues

    # 1. Opening 0-3s hook pop/whoosh if none placed yet (참고 쇼츠 15편 기준: 0.00s 는 폭발음이 아니라 002_뿅 / 573_Whoosh)
    if not any(c["timestamp_sec"] <= 2.2 for c in raw_cues):
        hook_t = speech_onsets[0] if speech_onsets and speech_onsets[0] <= 1.2 else min(0.20, duration_sec * 0.06)
        hook_cat = "pop" if preset_id != "clean" else "whoosh"
        raw_cues.append(
            {
                "timestamp_sec": hook_t,
                "trigger_type": "hook_0_3s",
                "sfx_category": hook_cat,
                "desired_sfx_query_en": CATEGORY_DEFAULT_QUERY[hook_cat],
                "desired_mood": "attention_grabbing",
                "intensity": 4,
                "target_db": accent_db,
                "duck_under_speech": True,
                "max_duration_sec": 1.2,
                "director_reason_ko": f"[{spec['label_ko']}] 초반 3초 시선 고정 오프닝 후킹 포인트",
            }
        )

    # 2. Subtitle semantic & color-markup rules (money, shock/red, deal/fail, solo interjections, yellow keywords)
    money_count = sum(1 for c in raw_cues if normalize_category(str(c.get("sfx_category", ""))) == "cash")
    for sub in subtitles:
        txt = sub.text
        clean = re.sub(r"\[(\w+:)?|\]", "", txt).strip()
        already_seeded = any(abs(float(c["timestamp_sec"]) - sub.start_sec) <= 0.08 for c in raw_cues)
        is_money = (
            sub.icon == "money"
            or "[green:" in txt
            or bool(re.search(r"\d[^a-zA-Z가-힣]*(억|만\s?원|천만|백만|달러|원)|완판|품절", clean))
        )
        if already_seeded and is_money:
            continue
        if is_money and (money_count == 0 or (spec["include_secondary_money"] and money_count < (3 if preset_id == "punchy" else 2))):
            use_cash = money_count == 0
            cat = "cash" if use_cash else "ding"
            raw_cues.append(
                {
                    "timestamp_sec": sub.start_sec,
                    "trigger_type": "money_stat",
                    "sfx_category": cat,
                    "desired_sfx_query_en": CATEGORY_DEFAULT_QUERY[cat],
                    "desired_mood": "exciting",
                    "intensity": 5 if use_cash else 4,
                    "target_db": accent_db if use_cash else round(accent_db - 0.8, 1),
                    "duck_under_speech": True,
                    "max_duration_sec": 1.6,
                    "exact_anchor": True,
                    "anchor_source": "subtitle_onset",
                    "matched_subtitle_text": clean,
                    "director_reason_ko": f"핵심 매출·금액 자막('{clean[:18]}') 강조",
                }
            )
            money_count += 1
        elif re.search(r"모두 아웃|전원 거절|빈손|멈췄다고|파산|실패", clean):
            raw_cues.append(
                {
                    "timestamp_sec": sub.start_sec,
                    "trigger_type": "mood_shift",
                    "sfx_category": "fail",
                    "desired_sfx_query_en": CATEGORY_DEFAULT_QUERY["fail"],
                    "desired_mood": "dramatic",
                    "intensity": 4,
                    "target_db": accent_db,
                    "duck_under_speech": True,
                    "max_duration_sec": 1.8,
                    "exact_anchor": True,
                    "anchor_source": "subtitle_onset",
                    "matched_subtitle_text": clean,
                    "director_reason_ko": f"거절·실패 반전 자막('{clean[:18]}') 강조",
                }
            )
        elif re.search(r"거래하죠|거래 성사|대박|완판|인수|성공", clean):
            raw_cues.append(
                {
                    "timestamp_sec": sub.start_sec,
                    "trigger_type": "mood_shift",
                    "sfx_category": "success",
                    "desired_sfx_query_en": CATEGORY_DEFAULT_QUERY["success"],
                    "desired_mood": "celebratory",
                    "intensity": 4,
                    "target_db": accent_db,
                    "duck_under_speech": True,
                    "max_duration_sec": 1.8,
                    "exact_anchor": True,
                    "anchor_source": "subtitle_onset",
                    "matched_subtitle_text": clean,
                    "director_reason_ko": f"거래 성사·성공 포인트('{clean[:18]}') 강조",
                }
            )
        elif spec["include_solo_pops"] and (sub.solo or SOLO_INTERJECTION_RE.match(clean)):
            raw_cues.append(
                {
                    "timestamp_sec": sub.start_sec,
                    "trigger_type": "clip_reaction",
                    "sfx_category": "surprise" if preset_id == "punchy" else "pop",
                    "desired_sfx_query_en": CATEGORY_DEFAULT_QUERY["surprise" if preset_id == "punchy" else "pop"],
                    "desired_mood": "snappy",
                    "intensity": 3,
                    "target_db": round(accent_db - 0.5, 1),
                    "duck_under_speech": True,
                    "max_duration_sec": 1.2,
                    "exact_anchor": True,
                    "anchor_source": "subtitle_onset",
                    "matched_subtitle_text": clean,
                    "director_reason_ko": f"해외쇼쇼 단독 감탄사('{clean}') 리액션 타격",
                }
            )
        elif re.search(r"\?\!|\?\?\?|;;|뭐라고|제정신", clean) and preset_id != "clean":
            raw_cues.append(
                {
                    "timestamp_sec": sub.start_sec,
                    "trigger_type": "clip_reaction",
                    "sfx_category": "question" if ";;" in clean or "??" in clean else "surprise",
                    "desired_sfx_query_en": CATEGORY_DEFAULT_QUERY["question"],
                    "desired_mood": "quirky",
                    "intensity": 3,
                    "target_db": round(accent_db - 0.5, 1),
                    "duck_under_speech": True,
                    "max_duration_sec": 1.4,
                    "exact_anchor": True,
                    "anchor_source": "subtitle_onset",
                    "matched_subtitle_text": clean,
                    "director_reason_ko": f"리액션·의문 자막('{clean[:18]}') 포인트",
                }
            )
        elif "[red:" in txt and preset_id != "clean":
            raw_cues.append(
                {
                    "timestamp_sec": sub.start_sec,
                    "trigger_type": "caption_pop",
                    "sfx_category": "surprise",
                    "desired_sfx_query_en": CATEGORY_DEFAULT_QUERY["surprise"],
                    "desired_mood": "tense",
                    "intensity": 3,
                    "target_db": float(spec["default_sfx_db"]),
                    "duck_under_speech": True,
                    "max_duration_sec": 1.4,
                    "exact_anchor": True,
                    "anchor_source": "subtitle_onset",
                    "matched_subtitle_text": clean,
                    "director_reason_ko": f"빨간 강조어('{clean[:18]}') 경고·반전 강조",
                }
            )
        elif spec["include_yellow_pops"] and "[yellow:" in txt and sub.start_sec > 1.2:
            raw_cues.append(
                {
                    "timestamp_sec": sub.start_sec,
                    "trigger_type": "caption_pop",
                    "sfx_category": "pop",
                    "desired_sfx_query_en": CATEGORY_DEFAULT_QUERY["pop"],
                    "desired_mood": "snappy",
                    "intensity": 2,
                    "target_db": cut_db,
                    "duck_under_speech": True,
                    "max_duration_sec": 0.9,
                    "exact_anchor": True,
                    "anchor_source": "subtitle_onset",
                    "matched_subtitle_text": clean,
                    "director_reason_ko": f"노란 핵심 키워드('{clean[:18]}') 톡 강조",
                }
            )

    # 3. Hero swell riser lead-in for punchy preset (쉬이익 차오름 -> 쿵/카칭!)
    if spec["hero_swell_lead_in"]:
        swell_cues: List[Dict[str, Any]] = []
        for hc in raw_cues:
            cat = normalize_category(str(hc.get("sfx_category", "")))
            t_hit = float(hc.get("timestamp_sec", 0.0))
            if cat in {"impact", "cash", "success"} and t_hit >= 1.1:
                swell_t = round(max(0.0, t_hit - 0.42), 3)
                if all(abs(swell_t - float(x["timestamp_sec"])) >= 0.35 for x in raw_cues + swell_cues):
                    swell_cues.append(
                        {
                            "timestamp_sec": swell_t,
                            "trigger_type": "mood_shift",
                            "sfx_category": "swell",
                            "desired_sfx_query_en": CATEGORY_DEFAULT_QUERY["swell"],
                            "desired_mood": "anticipation",
                            "intensity": 3,
                            "target_db": round(accent_db - 2.5, 1),
                            "duck_under_speech": True,
                            "max_duration_sec": 0.65,
                            "exact_anchor": True,
                            "anchor_source": "riser_lead_in",
                            "director_reason_ko": f"{t_hit:.2f}s 하이라이트 직전 차오름(라이저) 빌드업",
                        }
                    )
        raw_cues.extend(swell_cues)

    # 4. Pace-controlled visual cut whooshes/dings/pops tuned to preset cut_spacing
    occupied = [float(c["timestamp_sec"]) for c in raw_cues]
    toggle_alt = 0
    for cut_sec in visual_cuts:
        if cut_sec < 0.9 or cut_sec > duration_sec - 0.45:
            continue
        if all(abs(cut_sec - oc) >= cut_spacing for oc in occupied):
            if preset_id == "punchy":
                cycle = ("whoosh", "pop", "ding")
                cat = cycle[toggle_alt % 3]
            else:
                cat = "whoosh" if toggle_alt % 3 != 2 else "ding"
            toggle_alt += 1
            raw_cues.append(
                {
                    "timestamp_sec": cut_sec,
                    "trigger_type": "scene_cut",
                    "sfx_category": cat,
                    "desired_sfx_query_en": CATEGORY_DEFAULT_QUERY[cat],
                    "desired_mood": "snappy",
                    "intensity": 3 if preset_id != "clean" else 2,
                    "target_db": cut_db,
                    "duck_under_speech": True,
                    "max_duration_sec": 1.2,
                    "exact_anchor": True,
                    "anchor_source": "visual_cut",
                    "director_reason_ko": f"[{spec['label_ko']}] 장면 전환({cut_sec:.2f}s) 리듬 보강",
                }
            )
            occupied.append(cut_sec)

    return raw_cues


def _generate_cuesheet_via_agy_cli(
    video_path: Path,
    duration_sec: float,
    visual_cuts: List[float],
    subtitles: List[SubtitleEvent],
    edl_hints: List[Tuple[float, str]] | None,
    preset_id: str = "balanced",
) -> Optional[Dict[str, Any]]:
    """Invoke local Antigravity CLI (`agy -p`) with 해외쇼쇼 preset intensity/density targets."""
    agy_bin = find_agy_cli()
    if not agy_bin:
        return None
    spec = get_style_preset_spec(preset_id)

    try:
        rel_video = video_path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
        video_ref = f"@{rel_video}"
    except ValueError:
        video_ref = str(video_path.resolve())

    sub_lines = "\n".join(f"- [{s.start_sec:.2f}s~{s.end_sec:.2f}s] {s.text}" for s in subtitles[:55]) or "(없음)"
    prompt = (
        f"{video_ref} 초안 쇼츠 영상(총 {duration_sec:.2f}초)과 아래 정밀 타임라인을 참고해 "
        f"'해외쇼쇼 {spec['label_ko']}' 스타일(분당 약 {spec['max_cues_per_minute']}개, 기본 볼륨 {spec['default_sfx_db']}dB, 최소 간격 {spec['min_cue_gap_sec']}초)로 효과음 큐시트 JSON만 출력해 줘.\n"
        f"- 스타일 설명: {spec['desc_ko']}\n"
        f"- 샷/컷 전환 시각(초): {visual_cuts[:40]}\n"
        f"- 기존 EDL 힌트: {edl_hints or []}\n"
        f"- 자막 타임라인:\n{sub_lines}\n\n"
        f"허용 sfx_category: {STANDARD_SFX_CATEGORIES}\n"
        f"허용 trigger_type: {TRIGGER_TYPES}\n"
        '반드시 순수 JSON 객체 하나만 출력: {"overall_mood":"...","summary_ko":"...","cues":[{"timestamp":"00:01.35","timestamp_sec":1.35,"trigger_type":"hook_0_3s","sfx_category":"impact","desired_sfx_query_en":"deep cinematic hit","desired_mood":"punchy","intensity":4,"target_db":-14.0,"duck_under_speech":true,"max_duration_sec":1.8,"director_reason_ko":"..."}]}'
    )
    try:
        proc = subprocess.run(
            [agy_bin, "-p", prompt],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        if proc.returncode == 0 and proc.stdout:
            m = re.search(r"\{.*\}", proc.stdout, re.S)
            if m:
                return json.loads(m.group(0))
    except Exception as exc:
        logger.warning("agy CLI cuesheet call failed, falling back to local-free: %s", exc)
    return None


def generate_sfx_cuesheet(
    video_path: Path,
    config: SFXConfig,
    output_json_path: Path | None = None,
    subtitle_path: Path | None = None,
    edl_hints: List[Tuple[float, str]] | None = None,
    edl_sub_list: List[Dict[str, Any]] | None = None,
    edl_items: List[Dict[str, Any]] | None = None,
    backend_override: str | None = None,
    style_preset: str | None = None,
) -> SFXCuesheet:
    """Generate a frame-accurate SFX cuesheet tuned to the selected 해외쇼쇼 style preset."""
    preset_id = normalize_style_preset(style_preset or config.style_preset)
    active_cfg = config.with_style_preset(preset_id)
    spec = SFX_STYLE_PRESETS[preset_id]

    meta = probe_video_metadata(video_path, ffprobe_bin=active_cfg.ffprobe_bin)
    duration_sec = meta["duration_sec"]
    fps = meta["fps"]

    edl_shot_cuts: List[float] = []
    if edl_items:
        for it in edl_items:
            for sh in it.get("shots", []):
                t_cut = float(sh[0]) if isinstance(sh, (list, tuple)) else float(sh.get("a", 0.0))
                if t_cut > 0.05:
                    edl_shot_cuts.append(round(t_cut, 3))
    visual_cuts = sorted(set(edl_shot_cuts + detect_visual_cuts_ffmpeg(video_path, ffmpeg_bin=active_cfg.ffmpeg_bin)))
    speech_onsets = extract_speech_onsets_ffmpeg(video_path, ffmpeg_bin=active_cfg.ffmpeg_bin)

    if edl_sub_list:
        subtitles = _sub_events_from_edl_sub_list(edl_sub_list)
    else:
        sub_file = subtitle_path or find_companion_subtitle_file(video_path)
        subtitles = parse_subtitle_file(sub_file) if (sub_file and sub_file.is_file()) else []
        if subtitles and active_cfg.auto_sync_subtitles and speech_onsets and (not sub_file or sub_file.suffix.lower() == ".srt"):
            subtitles = snap_subtitles_to_speech_onsets(subtitles, speech_onsets)
            write_srt_file(subtitles, video_path.with_name(f"{video_path.stem}.synced.srt"))

    seed_hint_cues: List[Dict[str, Any]] = []
    for t_val, cat_raw in (edl_hints or []):
        base_cat = normalize_category(cat_raw)
        trig = "money_stat" if base_cat == "cash" else ("hook_0_3s" if t_val <= 2.8 else "scene_cut")
        seed_hint_cues.append(
            {
                "timestamp_sec": float(t_val),
                "trigger_type": trig,
                "sfx_category": cat_raw,
                "desired_sfx_query_en": CATEGORY_DEFAULT_QUERY.get(base_cat, f"{base_cat} sound effect"),
                "desired_mood": "punchy",
                "intensity": 4 if base_cat in {"impact", "cash"} else 3,
                "target_db": float(spec["hook_db"]) if base_cat == "impact" else float(spec["accent_db"]),
                "duck_under_speech": True,
                "max_duration_sec": 1.8,
                "exact_anchor": True,
                "anchor_source": "edl_exact",
                "director_reason_ko": f"EDL 지정 이벤트({cat_raw}) 동기화",
            }
        )

    effective_backend = active_cfg.resolved_backend
    if backend_override:
        ov = backend_override.strip().lower()
        if ov in {"local-free", "agy-cli", "gemini-api"}:
            effective_backend = ov
        elif ov == "auto":
            effective_backend = active_cfg.resolved_backend

    cuesheet: Optional[SFXCuesheet] = None

    if effective_backend == "agy-cli":
        agy_data = _generate_cuesheet_via_agy_cli(video_path, duration_sec, visual_cuts, subtitles, edl_hints, preset_id=preset_id)
        if agy_data and agy_data.get("cues"):
            merged = [c for c in seed_hint_cues if "/" in str(c.get("sfx_category", "")) or c.get("sfx_category") == "cash"] + agy_data["cues"]
            cues = _normalize_snap_and_filter_cues(merged, duration_sec, visual_cuts, subtitles, speech_onsets, active_cfg)
            cuesheet = SFXCuesheet(
                video_path=str(video_path),
                video_duration_sec=duration_sec,
                fps=fps,
                overall_mood=f"agy_{preset_id}",
                summary_ko=f"[agy CLI · {spec['label_ko']}] {agy_data.get('summary_ko', '')}".strip(),
                cues=cues,
            )

    elif effective_backend == "gemini-api" and active_cfg.gemini_api_key:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=active_cfg.gemini_api_key)
        schema = {
            "type": "OBJECT",
            "properties": {
                "overall_mood": {"type": "STRING"},
                "summary_ko": {"type": "STRING"},
                "cues": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "timestamp": {"type": "STRING"},
                            "timestamp_sec": {"type": "NUMBER"},
                            "trigger_type": {"type": "STRING", "enum": TRIGGER_TYPES},
                            "sfx_category": {"type": "STRING", "enum": STANDARD_SFX_CATEGORIES},
                            "desired_sfx_query_en": {"type": "STRING"},
                            "desired_mood": {"type": "STRING"},
                            "intensity": {"type": "INTEGER"},
                            "target_db": {"type": "NUMBER"},
                            "duck_under_speech": {"type": "BOOLEAN"},
                            "max_duration_sec": {"type": "NUMBER"},
                            "matched_subtitle_text": {"type": "STRING"},
                            "director_reason_ko": {"type": "STRING"},
                        },
                        "required": [
                            "timestamp", "timestamp_sec", "trigger_type", "sfx_category",
                            "desired_sfx_query_en", "desired_mood", "intensity", "target_db",
                            "duck_under_speech", "director_reason_ko",
                        ],
                    },
                },
            },
            "required": ["overall_mood", "summary_ko", "cues"],
        }

        sub_table = "\n".join(f"  - [{s.start_sec:.2f}s ~ {s.end_sec:.2f}s] {s.text}" for s in subtitles[:65]) or "  (화면 번인 자막 직접 참조)"
        prompt = (
            f"당신은 '해외쇼쇼' 스타일 60초 쇼츠 사운드 디렉터입니다. 총 길이 {duration_sec:.2f}초 ({fps:.2f}fps).\n"
            f"- 선택된 프리셋: {spec['label_ko']} ({spec['badge_ko']}) — {spec['desc_ko']}\n"
            f"- 목표 밀도: 분당 최대 {spec['max_cues_per_minute']}개, 최소 간격 {spec['min_cue_gap_sec']}초\n"
            f"- 목표 음압: 기본 {spec['default_sfx_db']}dB (범위 {spec['min_sfx_db']}dB ~ {spec['max_sfx_db']}dB)\n"
            f"- 샷/컷 전환 시각: {visual_cuts[:45]}\n"
            f"- 음성 시작점: {speech_onsets[:50]}\n"
            f"- 자막 타임라인:\n{sub_table}\n\n"
            "영상을 직접 시청하며 위 프리셋의 밀도와 음압 기준에 맞춰 최적의 효과음 큐시트를 작성하세요."
        )
        uploaded_video = None
        try:
            uploaded_video = client.files.upload(
                file=str(video_path),
                config=types.UploadFileConfig(mime_type="video/mp4", display_name=video_path.name),
            )
            while uploaded_video.state and uploaded_video.state.name == "PROCESSING":
                time.sleep(2.0)
                uploaded_video = client.files.get(name=uploaded_video.name)

            resp = client.models.generate_content(
                model=active_cfg.gemini_video_model,
                contents=[uploaded_video, prompt],
                config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=schema, temperature=0.2),
            )
            data = json.loads(resp.text)
            merged_raw = [c for c in seed_hint_cues if "/" in str(c.get("sfx_category", "")) or c.get("sfx_category") == "cash"] + data.get("cues", [])
            cues = _normalize_snap_and_filter_cues(merged_raw, duration_sec, visual_cuts, subtitles, speech_onsets, active_cfg)
            cuesheet = SFXCuesheet(
                video_path=str(video_path),
                video_duration_sec=duration_sec,
                fps=fps,
                overall_mood=f"gemini_{preset_id}",
                summary_ko=f"[Gemini 시청 · {spec['label_ko']}] {data.get('summary_ko', '')}".strip(),
                cues=cues,
            )
        except Exception as exc:
            logger.warning("Gemini video cuesheet failed (%s); falling back cleanly to local-free engine.", exc)
        finally:
            if uploaded_video is not None:
                try:
                    client.files.delete(name=uploaded_video.name)
                except Exception:
                    pass

    if cuesheet is None:
        raw_cues = _build_smart_local_cues(seed_hint_cues, visual_cuts, subtitles, speech_onsets, duration_sec, preset_id=preset_id)
        cues = _normalize_snap_and_filter_cues(raw_cues, duration_sec, visual_cuts, subtitles, speech_onsets, active_cfg)
        cuesheet = SFXCuesheet(
            video_path=str(video_path),
            video_duration_sec=duration_sec,
            fps=fps,
            overall_mood=f"local_free_{preset_id}",
            summary_ko=f"[무료 로컬 · {spec['label_ko']}] {spec['badge_ko']}",
            cues=cues,
        )

    if output_json_path is None:
        active_cfg.cuesheet_dir.mkdir(parents=True, exist_ok=True)
        output_json_path = active_cfg.cuesheet_dir / f"{video_path.stem}_sfx_cuesheet.json"
    else:
        output_json_path.parent.mkdir(parents=True, exist_ok=True)

    output_json_path.write_text(json.dumps(cuesheet.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return cuesheet
