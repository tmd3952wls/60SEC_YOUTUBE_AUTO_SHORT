"""웹 에디터 전용 원클릭 신규 쇼츠 작업 생성 워커.

유튜브 URL(또는 로컬 mp4 경로) + 제목·주제 힌트만으로:
1) 원본 다운로드 및 1920x1080 30fps 구간 추출 (source.mp4)
2) 음성 전사 (transcript.json) + 어절 타임스탬프 생성 (transcript_words.json, WhisperX 미설치 시 비율 폴백)
3) AI 대본 생성 (Claude/Antigravity CLI · API 또는 0원 스타터 초안)
4) 웹 에디터 전용 편집본 (v1_edl.json) 자동 변환 (해외쇼쇼 규칙·감탄사 단독 자막·기본 크롭 반영)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from shorts.common import JOBS, load_config, read_json, write_json  # noqa: E402

SOLO_INTERJECTIONS = {"와우", "오와우", "맙소사", "오마이갓", "세상에", "헐", "대박"}
LEGACY_SFX_MAP = {"boom": "impact"}
# 하단 방송 자막 띠를 살짝 피한 깔끔한 기본 중앙 크롭 (1920x1080 기준)
DEFAULT_CROP = [960, 495, 950]


def plain_text(text: str) -> str:
    return re.sub(r"\[(\w+:)?|\]", "", str(text or ""))


def sanitize_brand_rules(text: str) -> str:
    """해외쇼쇼 금칙어('샤크' → '투자자') 자동 정돈."""
    if not text:
        return ""
    return str(text).replace("샤크들", "투자자들").replace("샤크", "투자자")


def tokenize_preserving_spans(text: str) -> list[str]:
    """[yellow:140억 원] 처럼 대괄호 안에 공백이 있는 강조 구간을 쪼개지 않고 어절 단위로 분리."""
    tokens: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in str(text or "").strip():
        if ch == "[":
            depth += 1
            buf.append(ch)
        elif ch == "]":
            depth = max(0, depth - 1)
            buf.append(ch)
        elif ch.isspace() and depth == 0:
            if buf:
                tokens.append("".join(buf))
                buf = []
        else:
            buf.append(ch)
    if buf:
        tokens.append("".join(buf))
    return tokens


def split_narration_subs(text: str, max_chars: int = 12) -> list[dict]:
    """내레이션 문장을 웹 에디터 검사 규칙(plain 일치)을 100% 만족하는 자막 덩어리로 분할."""
    tokens = tokenize_preserving_spans(text)
    if not tokens:
        return [{"text": text}]
    chunks: list[str] = []
    cur = ""
    for tok in tokens:
        cand = f"{cur} {tok}".strip() if cur else tok
        if cur and len(plain_text(cand)) > max_chars:
            chunks.append(cur)
            cur = tok
        else:
            cur = cand
    if cur:
        chunks.append(cur)
    return [{"text": c} for c in chunks]


def is_solo_interjection(text: str) -> bool:
    norm = re.sub(r"[!?.~,\s|]", "", plain_text(text))
    return norm in SOLO_INTERJECTIONS


def parse_title_hint(title_hint: str) -> list[dict] | None:
    """사용자 제목 힌트를 2줄 상단 제목([{text, color}, {text, color}])으로 파싱."""
    raw = sanitize_brand_rules((title_hint or "").strip())
    if not raw:
        return None
    if "/" in raw or "\n" in raw:
        parts = [p.strip() for p in re.split(r"[/\n]+", raw) if p.strip()]
        if len(parts) >= 2:
            return [
                {"text": parts[0][:16], "color": "yellow"},
                {"text": parts[1][:16], "color": "white"},
            ]
    # 한 줄로 길게 적은 경우 가운데 공백 기준으로 2줄 분할
    if len(raw) <= 11:
        return [
            {"text": raw, "color": "yellow"},
            {"text": "과연 정체는?!", "color": "white"},
        ]
    spaces = [m.start() for m in re.finditer(r"\s+", raw)]
    if spaces:
        mid = len(raw) // 2
        cut = min(spaces, key=lambda idx: abs(idx - mid))
        l1, l2 = raw[:cut].strip(), raw[cut:].strip()
        return [
            {"text": l1[:16], "color": "yellow"},
            {"text": l2[:16], "color": "white"},
        ]
    return [
        {"text": raw[:11], "color": "yellow"},
        {"text": raw[11:22] or "놀라운 반전?!", "color": "white"},
    ]


def ensure_words_with_fallback(job_dir: Path, transcript: list[dict], cfg: dict) -> dict[str, list[dict]]:
    """WhisperX 어절 정렬을 우선 시도하고, 누락된 줄은 글자 수 비례 단어 시간으로 안전하게 채움."""
    from shorts.align import ensure_words

    words_path = job_dir / "transcript_words.json"
    words_map: dict[str, list[dict]] = {}
    try:
        loaded = ensure_words(job_dir, cfg)
        if isinstance(loaded, dict):
            words_map = loaded
    except Exception as exc:
        print(f"  ⚠ WhisperX 어절 정렬 생략 ({exc}) → 글자 비율 타임스탬프 사용")

    changed = False
    for row in transcript:
        key = str(row["id"])
        if words_map.get(key):
            continue
        raw_tokens = [w for w in str(row.get("text") or "").split() if w.strip()]
        if not raw_tokens:
            raw_tokens = ["..."]
        t0 = float(row.get("start", 0.0))
        t1 = max(t0 + 0.25, float(row.get("end", t0 + 1.0)))
        span = t1 - t0
        total_chars = sum(max(1, len(w)) for w in raw_tokens)
        cur = t0
        built = []
        for w in raw_tokens:
            dur = span * (max(1, len(w)) / total_chars)
            built.append({"w": w, "s": round(cur, 3), "e": round(cur + dur, 3)})
            cur += dur
        words_map[key] = built
        changed = True

    if changed or not words_path.is_file():
        write_json(words_path, words_map)
    return words_map


def build_starter_plan(transcript: list[dict], title_hint: str = "", context: str = "") -> dict:
    """외부 LLM CLI/API 없이도 웹 에디터에서 즉시 편집을 시작할 수 있는 0원 스타터 대본 생성."""
    parsed_titles = parse_title_hint(title_hint) or [
        {"text": "해외에서 난리 난", "color": "yellow"},
        {"text": "신기한 아이디어?!", "color": "white"},
    ]
    topic = sanitize_brand_rules((title_hint or context or "화제의 제품").replace("/", " ").strip())
    if len(topic) > 22:
        topic = topic[:22].strip()

    if not transcript:
        return {
            "title_lines": parsed_titles,
            "segments": [
                {
                    "type": "narration",
                    "text": f"[yellow:{topic}], 도대체 어떤 이야기인지 바로 보자",
                    "broll_id": 0,
                    "sfx": "whoosh",
                }
            ],
        }

    ids = [int(r["id"]) for r in transcript]
    first_id = ids[0]
    mid_idx = min(len(ids) - 1, max(1, len(ids) // 3))
    deal_idx = min(len(ids) - 1, max(mid_idx, (len(ids) * 2) // 3))
    last_id = ids[-1]

    segments: list[dict] = [
        {
            "type": "narration",
            "text": f"출시하자마자 화제가 된 [yellow:{topic}] 이야기인데",
            "broll_id": first_id,
            "sfx": "whoosh",
        },
        {
            "type": "narration",
            "text": "기존의 불편함을 간단한 아이디어 하나로 해결했다고 해",
            "broll_id": ids[min(1, len(ids) - 1)],
            "sfx": "pop",
        },
    ]

    # 대표 시연·대화 클립 1~2개 자동 배치
    clip1_id = ids[mid_idx]
    tr_by_id = {int(r["id"]): r for r in transcript}
    segments.append(
        {
            "type": "clip",
            "from_id": clip1_id,
            "to_id": clip1_id,
            "subs": [tr_by_id[clip1_id]["text"][:36] or "(원본 대사 번역 입력)"],
            "sfx": None,
        }
    )
    if deal_idx != clip1_id:
        clip2_id = ids[deal_idx]
        segments.append(
            {
                "type": "narration",
                "text": "과연 투자자들의 반응은 어땠을까",
                "broll_id": clip2_id,
                "sfx": "ding",
            }
        )
        segments.append(
            {
                "type": "clip",
                "from_id": clip2_id,
                "to_id": clip2_id,
                "subs": [tr_by_id[clip2_id]["text"][:36] or "(투자자 반응 번역 입력)"],
                "sfx": None,
            }
        )

    segments.append(
        {
            "type": "narration",
            "text": "방송 이후에도 꾸준히 주목받고 있다고 하네",
            "broll_id": last_id,
            "sfx": "success",
        }
    )
    return {"title_lines": parsed_titles, "segments": segments}


def normalize_title_lines(raw_titles: list, title_hint: str = "") -> list[dict]:
    """상단 2줄 제목 정규화 ('/' 나 줄바꿈으로 직접 2줄을 지정한 경우 사용자 힌트 우선)."""
    explicit_two_line = ("/" in (title_hint or "")) or ("\n" in (title_hint or ""))
    if explicit_two_line:
        parsed = parse_title_hint(title_hint)
        if parsed:
            return parsed

    norm: list[dict] = []
    default_colors = ["yellow", "white"]
    for idx, item in enumerate(raw_titles or []):
        if isinstance(item, dict):
            txt = sanitize_brand_rules(item.get("text", "")).strip()
            col = item.get("color") or default_colors[min(idx, 1)]
        else:
            txt = sanitize_brand_rules(str(item)).strip()
            col = default_colors[min(idx, 1)]
        if txt:
            norm.append({"text": txt, "color": col})

    if not norm and title_hint:
        parsed = parse_title_hint(title_hint)
        if parsed:
            return parsed

    while len(norm) < 2:
        norm.append(
            {
                "text": "화제의 아이디어" if len(norm) == 0 else "과연 결과는?!",
                "color": default_colors[len(norm)],
            }
        )
    return norm[:2]


def plan_to_edl(
    plan: dict,
    transcript: list[dict],
    words_map: dict[str, list[dict]],
    cfg: dict,
    title_hint: str = "",
) -> dict:
    """plan.json 구조를 웹 에디터·EDL 렌더러 호환 v1_edl.json 으로 변환."""
    tr_by_id = {int(r["id"]): r for r in transcript}
    fallback_start = float(transcript[0]["start"]) if transcript else 0.0
    sub_cfg = cfg.get("subtitle", {})
    max_chars = int(sub_cfg.get("narr_max_chars", sub_cfg.get("max_chars", 12)))
    title_lines = normalize_title_lines(plan.get("title_lines") or [], title_hint=title_hint)

    edl_items: list[dict] = []
    for seg in plan.get("segments") or []:
        seg_type = seg.get("type")
        raw_sfx = seg.get("sfx")
        sfx = LEGACY_SFX_MAP.get(raw_sfx, raw_sfx) if raw_sfx else None

        if seg_type == "narration":
            text = sanitize_brand_rules(seg.get("text", "")).strip()
            if not text:
                continue
            broll_id = seg.get("broll_id")
            src_sec = float(tr_by_id[int(broll_id)]["start"]) if broll_id in tr_by_id else fallback_start
            item: dict = {
                "type": "narration",
                "text": text,
                "subs": split_narration_subs(text, max_chars=max_chars),
                "shots": [
                    {
                        "src": round(max(0.0, src_sec), 2),
                        "crop": list(DEFAULT_CROP),
                        "why": "초안 자동 배치",
                    }
                ],
            }
            if sfx:
                item["sfx"] = sfx
            edl_items.append(item)

        elif seg_type == "clip":
            from_id = int(seg.get("from_id", 0))
            to_id = int(seg.get("to_id", from_id))
            ids = [i for i in range(from_id, to_id + 1) if i in tr_by_id]
            if not ids:
                continue

            raw_subs = list(seg.get("subs") or [])
            clip_subs: list[dict] = []
            word_cursor = 0
            for idx_offset, line_id in enumerate(ids):
                line_words = words_map.get(str(line_id)) or []
                sub_str = sanitize_brand_rules(raw_subs[idx_offset] if idx_offset < len(raw_subs) else "").strip()
                if sub_str:
                    sub_obj: dict = {"text": sub_str, "at_word": word_cursor}
                    if is_solo_interjection(sub_str):
                        sub_obj["solo"] = True
                    clip_subs.append(sub_obj)
                word_cursor += len(line_words)

            if not clip_subs:
                first_txt = tr_by_id[ids[0]].get("text", "").strip()[:36] or "..."
                clip_subs = [{"text": first_txt, "at_word": 0}]
            else:
                clip_subs[0]["at_word"] = 0

            item = {
                "type": "clip",
                "ids": ids,
                "subs": clip_subs,
                "shots": [
                    {
                        "src": "sync",
                        "crop": list(DEFAULT_CROP),
                        "why": "원본 대사 장면",
                    }
                ],
            }
            if sfx:
                item["sfx"] = sfx
            edl_items.append(item)

    if not edl_items:
        starter = build_starter_plan(transcript, title_hint=title_hint)
        return plan_to_edl(starter, transcript, words_map, cfg, title_hint=title_hint)

    edl_doc: dict = {
        "title_lines": title_lines,
        "items": edl_items,
    }
    if plan.get("credit"):
        edl_doc["credit"] = plan["credit"]
    if plan.get("upload"):
        edl_doc["upload"] = plan["upload"]
    return edl_doc


def create_new_job(
    name: str,
    src: str,
    title_hint: str = "",
    context: str = "",
    start: float | None = None,
    end: float | None = None,
    script_mode: str = "auto",
) -> Path:
    from shorts import script, source

    cfg = load_config()
    if script_mode and script_mode != "starter":
        cfg = {**cfg, "script": {**cfg.get("script", {}), "mode": script_mode}}

    job_dir = JOBS / name
    job_dir.mkdir(parents=True, exist_ok=True)

    print(f"[1/4] 원본 영상 준비 중: {src}")
    video_path = job_dir / "source.mp4"
    if not video_path.is_file():
        video_path = source.fetch(src, job_dir, start=start, end=end)
    print(f"  → source.mp4 준비 완료 ({video_path.name})")

    print("[2/4] 원본 음성 전사 및 어절 시간 정렬 중...")
    tr_path = job_dir / "transcript.json"
    if tr_path.is_file():
        transcript = read_json(tr_path)
        print(f"  → 기존 transcript.json 재사용 ({len(transcript)}줄)")
    else:
        transcript = source.transcribe(video_path, job_dir, cfg.get("whisper_model", "small"))
        print(f"  → 음성 전사 완료 ({len(transcript)}줄)")
    words_map = ensure_words_with_fallback(job_dir, transcript, cfg)

    combined_ctx_parts = []
    if title_hint.strip():
        combined_ctx_parts.append(f"희망 제목/주제 힌트: {title_hint.strip()}")
    if context.strip():
        combined_ctx_parts.append(context.strip())
    combined_ctx = "\n".join(combined_ctx_parts)

    plan_path = job_dir / "plan.json"
    used_starter = False
    if script_mode == "starter":
        print("[3/4] 0원 스타터 초안 구성 모드 선택 → 전사본 기반 초안 생성 중...")
        script.build_prompt(job_dir, combined_ctx)
        plan = build_starter_plan(transcript, title_hint=title_hint, context=context)
        write_json(plan_path, plan)
        used_starter = True
    else:
        print(f"[3/4] 한국어 쇼츠 대본 작성 중 (모드: {script_mode})...")
        ok = script.generate(job_dir, cfg, combined_ctx)
        if ok and plan_path.is_file():
            plan = read_json(plan_path)
        else:
            print("  ℹ 자동 대본 엔진 미설정 → 웹 에디터에서 바로 편집할 수 있게 스타터 초안을 생성합니다 (prompt.txt 함께 저장됨).")
            plan = build_starter_plan(transcript, title_hint=title_hint, context=context)
            write_json(plan_path, plan)
            used_starter = True

    print("[4/4] 웹 에디터 편집본(v1_edl.json) 변환 및 해외쇼쇼 규칙 적용 중...")
    edl_doc = plan_to_edl(plan, transcript, words_map, cfg, title_hint=title_hint)
    edl_out = job_dir / "v1_edl.json"
    write_json(edl_out, edl_doc)

    narr_cnt = sum(1 for it in edl_doc["items"] if it["type"] == "narration")
    clip_cnt = sum(1 for it in edl_doc["items"] if it["type"] == "clip")
    mode_tag = "스타터 초안" if used_starter else "AI 자동 대본"
    print(f"완료: {name} · v1_edl.json ({mode_tag}, 내레이션 {narr_cnt}개 + 원본대사 {clip_cnt}개)")
    return edl_out


def main() -> None:
    ap = argparse.ArgumentParser(description="웹 에디터 신규 쇼츠 작업 생성 워커")
    ap.add_argument("--name", required=True, help="jobs/ 아래 생성할 작업 폴더 이름")
    ap.add_argument("--src", required=True, help="유튜브 URL 또는 로컬 동영상 경로")
    ap.add_argument("--title-hint", default="", help="상단 2줄 제목 또는 주제 힌트")
    ap.add_argument("--context", default="", help="프로그램명·맥락 메모")
    ap.add_argument("--start", type=float, default=None, help="원본 시작 시각(초)")
    ap.add_argument("--end", type=float, default=None, help="원본 끝 시각(초)")
    ap.add_argument(
        "--script-mode",
        default="auto",
        choices=["auto", "claude-cli", "agy-cli", "claude", "gemini", "openai", "starter"],
    )
    args = ap.parse_args()

    try:
        create_new_job(
            name=args.name,
            src=args.src,
            title_hint=args.title_hint,
            context=args.context,
            start=args.start,
            end=args.end,
            script_mode=args.script_mode,
        )
    except Exception as exc:
        print(f"오류: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
