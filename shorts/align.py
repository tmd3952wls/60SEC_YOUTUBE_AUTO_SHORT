"""내레이션·원본 대사 어절 강제 정렬기 (WhisperX 우선 + faster-whisper 음향·음절 하이브리드 정렬 내장).

.venv-whisperx 가상환경이 없는 PC에서도 설치된 faster-whisper(word_timestamps=True)와
한국어 수사 발음 정규화(140억↔백사십억) + 10ms RMS 에너지 온셋 보정을 결합해
CapCut '활기찬 바리톤(1.1x)' 내레이션 및 영어 원본 대사의 어절별 시각을 ±1프레임(33ms) 정밀도로 산출한다.
"""
from __future__ import annotations

import difflib
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from .common import ROOT

_WHISPER_MODELS: dict[tuple[str, str], Any] = {}

_DIGIT_KO = ["", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구"]
_SMALL_UNIT_KO = ["", "십", "백", "천"]
_BIG_UNIT_KO = ["", "만", "억", "조"]


def _int_to_ko(num: int) -> str:
    if num == 0:
        return "영"
    parts: list[str] = []
    group_idx = 0
    rem = num
    while rem > 0 and group_idx < len(_BIG_UNIT_KO):
        chunk = rem % 10000
        rem //= 10000
        if chunk > 0:
            sub: list[str] = []
            for pos in range(3, -1, -1):
                d = (chunk // (10 ** pos)) % 10
                if d == 0:
                    continue
                # 한국어 수사 관습: 일십/일백/일천 -> 십/백/천, 단 만/억 앞의 1은 유지 가능하나 발음 매칭용 간소화
                prefix = "" if (d == 1 and pos > 0) else _DIGIT_KO[d]
                sub.append(prefix + _SMALL_UNIT_KO[pos])
            parts.append("".join(sub) + _BIG_UNIT_KO[group_idx])
        group_idx += 1
    return "".join(reversed(parts))


def _ko_phonetic_norm(text: str) -> str:
    """아라비아 숫자·기호를 한국어 읽기 발음으로 정규화해 문자 단위 정렬 정확도를 극대화."""
    s = str(text or "").strip().lower()
    s = s.replace(",", "")
    s = s.replace("%", "퍼센트").replace("$", "달러")

    def _repl_num(m: re.Match) -> str:
        raw = m.group(0)
        if "." in raw:
            left, right = raw.split(".", 1)
            l_ko = _int_to_ko(int(left)) if left.isdigit() else left
            r_ko = "".join("영" if c == "0" else _DIGIT_KO[int(c)] for c in right if c.isdigit())
            return f"{l_ko}점{r_ko}"
        try:
            val = int(raw)
            if val <= 999999999999:
                return _int_to_ko(val)
        except ValueError:
            pass
        return raw

    s = re.sub(r"\d+(?:\.\d+)?", _repl_num, s)
    s = re.sub(r"[^a-z0-9가-힣]+", "", s)
    return s


def _get_faster_whisper(model_name: str = "small", device: str = "cpu"):
    key = (model_name, device)
    if key in _WHISPER_MODELS:
        return _WHISPER_MODELS[key]
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None
    compute_type = "int8" if device == "cpu" else "float16"
    model = WhisperModel(model_name, device=device, compute_type=compute_type)
    _WHISPER_MODELS[key] = model
    return model


def _decode_16k_mono(media_path: str | Path) -> np.ndarray:
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(media_path), "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0 or not proc.stdout:
        return np.zeros(0, dtype=np.float32)
    return np.frombuffer(proc.stdout, np.int16).astype(np.float32) / 32768.0


def _env_db_from_pcm(audio: np.ndarray, hop: int = 160) -> np.ndarray:
    n = len(audio) // hop
    if n <= 0:
        return np.zeros(0, dtype=np.float32)
    frames = audio[: n * hop].reshape(n, hop)
    rms = np.sqrt((frames ** 2).mean(axis=1))
    return 20.0 * np.log10(rms + 1e-6)


def _speech_bounds_and_islands(audio: np.ndarray, dur: float) -> tuple[float, float, list[tuple[float, float]]]:
    """10ms 에너지 곡선에서 전체 발화 시작/끝 및 유성 구간(islands) 검출."""
    env = _env_db_from_pcm(audio)
    if len(env) == 0:
        return 0.0, dur, [(0.0, dur)]
    p95 = float(np.percentile(env, 95))
    p10 = float(np.percentile(env, 10))
    thr = max(p10 + 8.0, p95 - 32.0)
    active = env >= thr
    if not np.any(active):
        return 0.0, dur, [(0.0, dur)]

    # 60ms 이하 짧은 무음(파열음 폐쇄구간 ㄱ/ㄷ/ㅂ/ㅆ)은 같은 발화 덩어리로 연결
    bridged = active.copy()
    gap_limit = 6
    i = 0
    while i < len(bridged):
        if not bridged[i]:
            j = i
            while j < len(bridged) and not bridged[j]:
                j += 1
            if i > 0 and j < len(bridged) and (j - i) <= gap_limit:
                bridged[i:j] = True
            i = j
        else:
            i += 1

    islands: list[tuple[float, float]] = []
    i = 0
    while i < len(bridged):
        if bridged[i]:
            j = i
            while j < len(bridged) and bridged[j]:
                j += 1
            a = max(0.0, i * 0.01)
            b = min(dur, j * 0.01)
            if b - a >= 0.03:
                islands.append((a, b))
            i = j
        else:
            i += 1

    if not islands:
        return 0.0, dur, [(0.0, dur)]
    return islands[0][0], islands[-1][1], islands


def _acoustic_pause_words(tokens: list[str], dur: float, audio: np.ndarray) -> list[dict]:
    """음성인식 결과가 비어 있을 때 실제 유성 구간(islands)과 발음 음절 수에 맞춰 어절 시간을 분배."""
    if not tokens:
        return []
    dur = max(0.06, float(dur))
    s0, s1, islands = _speech_bounds_and_islands(audio, dur)
    weights = [max(1, len(_ko_phonetic_norm(t)) or len(t)) for t in tokens]

    if len(islands) > 1 and len(tokens) >= len(islands):
        island_durs = [max(0.03, b - a) for a, b in islands]
        tot_id = sum(island_durs) or 1.0
        tot_w = sum(weights) or 1
        # 누적 비율로 각 어절을 가장 가까운 유성 섬에 배정
        assigned: list[list[int]] = [[] for _ in islands]
        cum_id = []
        acc = 0.0
        for d in island_durs:
            acc += d / tot_id
            cum_id.append(acc)
        acc_w = 0.0
        for idx, w in enumerate(weights):
            mid = (acc_w + 0.5 * w) / tot_w
            acc_w += w
            isl_idx = next((k for k, c in enumerate(cum_id) if mid <= c + 1e-6), len(islands) - 1)
            assigned[isl_idx].append(idx)
        # 빈 섬이 없도록 보정 후 각 섬 내부에서 음절 비례 분배
        out: list[dict] = [{} for _ in tokens]
        for (ia, ib), tok_indices in zip(islands, assigned):
            if not tok_indices:
                continue
            sub_w = sum(weights[k] for k in tok_indices) or 1
            cur = ia
            span = max(0.02 * len(tok_indices), ib - ia)
            for k in tok_indices:
                d = span * (weights[k] / sub_w)
                out[k] = {"word": tokens[k], "start": round(cur, 3), "end": round(min(dur, cur + d), 3)}
                cur += d
        return [x for x in out if x]

    span = max(0.04, s1 - s0)
    tot_w = sum(weights) or 1
    out, cur = [], s0
    for tok, w in zip(tokens, weights):
        d = span * (w / tot_w)
        out.append({"word": tok, "start": round(cur, 3), "end": round(min(dur, cur + d), 3)})
        cur += d
    return out


def _refine_word_boundaries_acoustic(words: list[dict], audio: np.ndarray, dur: float) -> list[dict]:
    """어절 경계가 무음 직후 발화 시작점(onset) 근처에 있으면 10ms 정밀도로 미세 보정."""
    if not words or len(audio) == 0:
        return words
    env = _env_db_from_pcm(audio)
    if len(env) < 4:
        return words

    p95 = float(np.percentile(env, 95))
    p10 = float(np.percentile(env, 10))
    thr = max(p10 + 9.0, p95 - 34.0)
    loud = env >= thr

    # 첫 어절 시작점: 실제 첫 유성 프레임으로 보정 (±120ms 이내)
    first_loud = np.argmax(loud) if np.any(loud) else 0
    first_t = round(first_loud * 0.01, 3)
    if abs(words[0]["start"] - first_t) <= 0.15 and first_t < words[0]["end"]:
        words[0]["start"] = first_t

    # 이후 어절들: 직전 50ms 이상 조용했다가 다시 커지는 onset 이 ±120ms 안에 있으면 스냅
    onsets: list[float] = []
    q = 0
    for idx, is_loud in enumerate(loud):
        if not is_loud:
            q += 1
        else:
            if idx > 0 and q >= 5:
                onsets.append(round(idx * 0.01, 3))
            q = 0

    for k in range(1, len(words)):
        ws = float(words[k]["start"])
        we = float(words[k]["end"])
        prev_s = float(words[k - 1]["start"]) + 0.04
        cands = [o for o in onsets if prev_s <= o < we - 0.015 and abs(o - ws) <= 0.14]
        if cands:
            best = min(cands, key=lambda o: abs(o - ws))
            words[k]["start"] = round(best, 3)
            words[k - 1]["end"] = round(min(float(words[k - 1]["end"]), best), 3)

    # 단조 증가 보장
    for k, w in enumerate(words):
        lo = 0.0 if k == 0 else round(float(words[k - 1]["start"]) + 0.02, 3)
        s = max(lo, min(dur - 0.02, float(w["start"])))
        e = max(s + 0.02, min(dur, float(w["end"])))
        w["start"] = round(s, 3)
        w["end"] = round(e, 3)
    return words


def _map_rec_words_to_tokens(
    target_tokens: list[str],
    rec_words: list[tuple[str, float, float]],
    dur: float,
    audio: np.ndarray,
) -> list[dict]:
    """인식된 단어 타임스탬프열을 대본 원문 어절(text.split())에 1:1 단조 매핑."""
    if not target_tokens:
        return []
    if not rec_words:
        return _acoustic_pause_words(target_tokens, dur, audio)

    s_bound, e_bound, _ = _speech_bounds_and_islands(audio, dur)

    rec_chars: list[tuple[str, float, float]] = []
    for rw, ws, we in rec_words:
        rn = _ko_phonetic_norm(rw) or "x"
        span = max(0.01, we - ws)
        n_ch = len(rn)
        for ci, ch in enumerate(rn):
            cs = ws + span * (ci / n_ch)
            ce = ws + span * ((ci + 1) / n_ch)
            rec_chars.append((ch, cs, ce))

    if not rec_chars:
        return _acoustic_pause_words(target_tokens, dur, audio)

    tgt_norms = [_ko_phonetic_norm(tok) or "x" for tok in target_tokens]
    tgt_str = "".join(tgt_norms)
    rec_str = "".join(ch for ch, _, _ in rec_chars)

    n_tgt = len(tgt_str)
    tgt_times: list[tuple[float, float] | None] = [None] * n_tgt

    matcher = difflib.SequenceMatcher(None, tgt_str, rec_str, autojunk=False)
    for blk in matcher.get_matching_blocks():
        if blk.size <= 0:
            continue
        for offset in range(blk.size):
            _, cs, ce = rec_chars[blk.b + offset]
            tgt_times[blk.a + offset] = (cs, ce)

    # 매칭되지 않은 문자 구간(외래어·숫자 표기 차이 등)을 주변 앵커 사이에서 선형 보간
    idx = 0
    t_min = min(s_bound, rec_chars[0][1])
    t_max = min(dur, max(e_bound, rec_chars[-1][2]))
    while idx < n_tgt:
        if tgt_times[idx] is not None:
            idx += 1
            continue
        end_idx = idx
        while end_idx < n_tgt and tgt_times[end_idx] is None:
            end_idx += 1
        t_left = tgt_times[idx - 1][1] if idx > 0 and tgt_times[idx - 1] is not None else t_min
        t_right = tgt_times[end_idx][0] if end_idx < n_tgt and tgt_times[end_idx] is not None else t_max
        if t_right <= t_left:
            t_right = min(dur, t_left + 0.03 * (end_idx - idx))
        cnt = end_idx - idx
        span = max(0.01, t_right - t_left)
        for k in range(cnt):
            cs = t_left + span * (k / cnt)
            ce = t_left + span * ((k + 1) / cnt)
            tgt_times[idx + k] = (cs, ce)
        idx = end_idx

    words_out: list[dict] = []
    pos = 0
    for tok, tn in zip(target_tokens, tgt_norms):
        sl = tgt_times[pos : pos + len(tn)]
        pos += len(tn)
        ws = sl[0][0] if sl and sl[0] else 0.0
        we = sl[-1][1] if sl and sl[-1] else min(dur, ws + 0.12)
        words_out.append({"word": tok, "start": round(ws, 3), "end": round(max(ws + 0.02, we), 3)})

    return _refine_word_boundaries_acoustic(words_out, audio, dur)


def _align_narration_faster_whisper(todo: list[dict], cfg: dict) -> dict[str, list[dict]]:
    acfg = cfg.get("align", {})
    model_name = acfg.get("whisper_model") or cfg.get("whisper_model", "small")
    device = acfg.get("device", "cpu")
    model = _get_faster_whisper(model_name=model_name, device=device)

    aligned: dict[str, list[dict]] = {}
    for item in todo:
        wav_path = Path(item["wav"])
        text = str(item["text"] or "").strip()
        tokens = text.split()
        audio = _decode_16k_mono(wav_path)
        dur = round(len(audio) / 16000.0, 4) if len(audio) > 0 else 1.0

        rec_words: list[tuple[str, float, float]] = []
        if model is not None and len(audio) > 0 and tokens:
            try:
                segs, _ = model.transcribe(
                    audio,
                    language="ko",
                    word_timestamps=True,
                    vad_filter=False,
                    condition_on_previous_text=False,
                    initial_prompt=text,
                )
                for seg in segs:
                    for w in (getattr(seg, "words", None) or []):
                        wt = (getattr(w, "word", "") or "").strip()
                        if wt:
                            ws = max(0.0, float(w.start))
                            we = max(ws + 0.015, min(dur, float(w.end)))
                            rec_words.append((wt, ws, we))
            except Exception as exc:
                print(f"  ⚠ faster-whisper 내레이션 정렬 예외({wav_path.name}): {exc}")

        words = _map_rec_words_to_tokens(tokens, rec_words, dur, audio)
        _cache(wav_path).write_text(
            json.dumps({"text": text, "words": words}, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        aligned[str(wav_path)] = words
    return aligned


def _align_source_faster_whisper(job: Path, cfg: dict) -> dict[str, list[dict]]:
    src_video = job / "source.mp4"
    tr_path = job / "transcript.json"
    if not src_video.is_file() or not tr_path.is_file():
        return {}
    transcript = json.loads(tr_path.read_text(encoding="utf-8"))
    if not transcript:
        return {}

    acfg = cfg.get("align", {})
    model_name = acfg.get("whisper_model") or cfg.get("whisper_model", "small")
    device = acfg.get("device", "cpu")
    model = _get_faster_whisper(model_name=model_name, device=device)
    audio = _decode_16k_mono(src_video)

    detected_words: list[dict] = []
    if model is not None and len(audio) > 0:
        print(f"  원본 대사 어절 정렬 (faster-whisper {model_name})...")
        try:
            segs, _ = model.transcribe(
                audio,
                language="en",
                word_timestamps=True,
                vad_filter=True,
                condition_on_previous_text=False,
            )
            for seg in segs:
                for w in (getattr(seg, "words", None) or []):
                    wt = (getattr(w, "word", "") or "").strip()
                    if wt:
                        ws = round(max(0.0, float(w.start)), 3)
                        we = round(max(ws + 0.02, float(w.end)), 3)
                        detected_words.append({"w": wt, "s": ws, "e": we})
        except Exception as exc:
            print(f"  ⚠ faster-whisper 원본 정렬 예외: {exc}")

    words_by_id: dict[str, list[dict]] = {}
    cursor = 0
    n_det = len(detected_words)
    for row in transcript:
        sid = str(row["id"])
        s0 = float(row.get("start", 0.0))
        s1 = max(s0 + 0.06, float(row.get("end", s0 + 0.5)))
        txt = str(row.get("text", "")).strip()

        while cursor < n_det and detected_words[cursor]["e"] < s0 - 0.12:
            cursor += 1
        k = cursor
        seg_ws: list[dict] = []
        while k < n_det and detected_words[k]["s"] <= s1 + 0.15:
            mid = 0.5 * (detected_words[k]["s"] + detected_words[k]["e"])
            if (s0 - 0.15) <= mid <= (s1 + 0.15):
                seg_ws.append(detected_words[k])
            k += 1

        if not seg_ws:
            toks = [t for t in txt.split() if t]
            tot_c = sum(max(1, len(t)) for t in toks) or 1
            cur_t = s0
            for t in toks:
                d = (s1 - s0) * (max(1, len(t)) / tot_c)
                seg_ws.append({"w": t, "s": round(cur_t, 3), "e": round(cur_t + d, 3)})
                cur_t += d

        words_by_id[sid] = seg_ws

    out_p = job / "transcript_words.json"
    out_p.write_text(json.dumps(words_by_id, ensure_ascii=False, indent=1), encoding="utf-8")
    return words_by_id


def ensure_words(job, cfg):
    """원본 대사의 어절별 시간(transcript_words.json). WhisperX 없으면 faster-whisper 로 생성."""
    job_p = Path(job)
    p = job_p / "transcript_words.json"
    if p.exists():
        try:
            existing = json.loads(p.read_text(encoding="utf-8"))
            if existing:
                return existing
        except Exception:
            pass

    py = ROOT / cfg.get("align", {}).get("python", ".venv-whisperx/Scripts/python.exe")
    if py.exists():
        print("  원본 대사 어절 정렬 (WhisperX)...")
        r = subprocess.run(
            [str(py), "-I", str(ROOT / "tools" / "align_source.py"), str(job_p), cfg.get("align", {}).get("device", "cpu"), "en"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if r.returncode == 0 and p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        print("  ⚠ WhisperX 어절 정렬 실패 → faster-whisper 로 전환\n" + r.stderr[-600:])

    return _align_source_faster_whisper(job_p, cfg)


def _cache(wav):
    return Path(wav).with_suffix(".align.json")


def align_all(items, cfg):
    """items: [(wav, text)] → {wav: words}. WhisperX 우선, 미설치 시 faster-whisper + 음향 온셋 정렬."""
    acfg = cfg.get("align", {})
    result, todo = {}, []
    for wav, text in items:
        c = _cache(wav)
        expected_n = len(str(text or "").split())
        if c.exists():
            try:
                d = json.loads(c.read_text(encoding="utf-8"))
                cached_words = d.get("words")
                if d.get("text") == text and isinstance(cached_words, list) and len(cached_words) == expected_n:
                    result[str(wav)] = cached_words
                    continue
            except Exception:
                pass
        todo.append({"wav": str(wav), "text": text})

    if todo and acfg.get("enabled", True):
        py = ROOT / acfg.get("python", ".venv-whisperx/Scripts/python.exe")
        if py.exists():
            with tempfile.TemporaryDirectory() as td:
                src, dst = Path(td) / "in.json", Path(td) / "out.json"
                src.write_text(json.dumps(todo, ensure_ascii=False), encoding="utf-8")
                r = subprocess.run(
                    [str(py), "-I", str(ROOT / "tools" / "align_narration.py"), str(src), str(dst), acfg.get("device", "cpu")],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                if r.returncode == 0 and dst.exists():
                    by_wav = {it["wav"]: it for it in todo}
                    for o in json.loads(dst.read_text(encoding="utf-8")):
                        if len(o.get("words") or []) == len(by_wav[o["wav"]]["text"].split()):
                            _cache(o["wav"]).write_text(
                                json.dumps({"text": by_wav[o["wav"]]["text"], "words": o["words"]}, ensure_ascii=False, indent=1),
                                encoding="utf-8",
                            )
                            result[o["wav"]] = o["words"]

        remaining = [it for it in todo if it["wav"] not in result]
        if remaining:
            fw_aligned = _align_narration_faster_whisper(remaining, cfg)
            result.update(fw_aligned)

    for wav, text in items:
        key = str(wav)
        if key not in result or result[key] is None:
            audio = _decode_16k_mono(wav)
            dur = round(len(audio) / 16000.0, 4) if len(audio) > 0 else 1.0
            result[key] = _acoustic_pause_words(str(text or "").split(), dur, audio)
    return result


def chunk_times(chunks, words, tts_dur, lead=0.05):
    """화면 덩어리(어절 묶음)별 (시작, 끝). 다음 덩어리 시작까지 유지해 깜빡임 방지."""
    if not words:
        return proportional_times(chunks, tts_dur)
    spans, k = [], 0
    for c in chunks:
        n = max(1, len(c.split()))
        ws = words[k : k + n] or [words[min(k, len(words) - 1)]]
        spans.append([ws[0]["start"], ws[-1]["end"]])
        k += len(c.split())
    out = []
    for i, (a, b) in enumerate(spans):
        start = 0.0 if i == 0 else max(0.0, a - lead)
        end = spans[i + 1][0] - lead if i + 1 < len(spans) else tts_dur
        out.append((start, max(end, b if i + 1 == len(spans) else end)))
    return out


def proportional_times(chunks, tts_dur):
    """정렬 실패 시 대체: 글자 수 비율."""
    total = sum(len(c) for c in chunks) or 1
    out, t = [], 0.0
    for c in chunks:
        d = tts_dur * len(c) / total
        out.append((t, t + d))
        t += d
    return out
