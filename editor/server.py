"""쇼츠 편집기 서버 (파이썬 기본 라이브러리만 사용, 이 컴퓨터에서만 접속 가능).

실행: python editor/server.py   →  http://127.0.0.1:47615
"""
import hashlib
import importlib.util
import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from auto_sfx.config import (  # noqa: E402
    SFX_STYLE_PRESETS,
    SFXConfig,
    find_agy_cli,
    load_favorite_stems,
    normalize_style_preset,
)
from auto_sfx.cuesheet import format_mmss_ms as format_mmss, generate_sfx_cuesheet  # noqa: E402
from auto_sfx.models import STANDARD_SFX_CATEGORIES, SFXCuesheet, normalize_category  # noqa: E402
from editor.sfx_worker import extract_edl_hints, parse_companion_log  # noqa: E402
from shorts.common import ASSETS, JOBS  # noqa: E402

STATIC = HERE / "static"
PRESETS = HERE / "presets"
ENV = ROOT / ".env"
CONFIG = ROOT / "config.json"
FAVORITES = ASSETS / "sfx_favorites.json"
CAPCUT_PENDING = JOBS / "_capcut_pending.json"
PORT = int(os.environ.get("EDITOR_PORT", "47615"))
KEY_NAMES = [
    "GEMINI_API_KEY",
    "TYPECAST_API_KEY",
    "FISH_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "FREESOUND_API_KEY",
    "ELEVENLABS_API_KEY",
]
VOICE_KO_NAMES = {
    "vibrant_baritone": "활기찬 바리톤 (Vibrant Baritone)",
}
SAY_MAP = {"ㄹㅇ": "진짜"}
NAME_RE = re.compile(r"^[^/\\:*?\"<>|]+$")

# ---------------------------------------------------------------- 작업(신규생성·렌더·색인·리믹스·CapCut) 한 번에 하나
TASK = {"kind": None, "running": False, "log": [], "out": None, "job": None, "ok": None, "started": 0}
TASK_LOCK = threading.Lock()


def start_task(kind, cmd, job=None, out=None):
    with TASK_LOCK:
        if TASK["running"]:
            return False
        TASK.update(kind=kind, running=True, log=[], out=out, job=job, ok=None, started=time.time())

    def run():
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        p = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding="utf-8", errors="replace", env=env)
        for line in p.stdout:
            TASK["log"].append(line.rstrip())
            del TASK["log"][:-400]
        p.stdout.close()
        p.wait()
        TASK.update(running=False, ok=p.returncode == 0)

    threading.Thread(target=run, daemon=True).start()
    return True


# ---------------------------------------------------------------- 도우미
def safe_job(name):
    if not name or not NAME_RE.match(name) or name.startswith("."):
        raise ValueError("잘못된 작업 이름")
    p = JOBS / name
    if not p.is_dir():
        raise FileNotFoundError(name)
    return p


def suggest_job_name(raw_name: str = "", title_hint: str = "", src: str = "") -> str:
    """사용자 입력 이름·제목 힌트·유튜브 URL 에서 안전하고 겹치지 않는 작업 폴더 이름 생성."""
    cand = (raw_name or "").strip()
    if not cand and title_hint:
        first_part = re.split(r"[/\n]+", title_hint.strip())[0]
        cleaned = re.sub(r"[/\\:*?\"<>|!?.~,]+", " ", first_part)
        cleaned = re.sub(r"\s+", "_", cleaned).strip("._ ")
        cand = cleaned[:20]
    if not cand and src:
        s = src.strip()
        m = (
            re.search(r"[?&]v=([A-Za-z0-9_-]{6,15})", s)
            or re.search(r"youtu\.be/([A-Za-z0-9_-]{6,15})", s)
            or re.search(r"/shorts/([A-Za-z0-9_-]{6,15})", s)
        )
        if m:
            cand = f"yt_{m.group(1)}"
        elif Path(s).stem:
            cand = re.sub(r"[/\\:*?\"<>|\s]+", "_", Path(s).stem).strip("._ ")[:20]
    if not cand:
        cand = time.strftime("short_%m%d_%H%M")

    cand = re.sub(r"[/\\:*?\"<>|]+", "_", cand).strip("._ ")
    if not cand or cand.startswith("."):
        cand = time.strftime("short_%m%d_%H%M")

    JOBS.mkdir(parents=True, exist_ok=True)
    base = cand
    idx = 2
    while (JOBS / cand).exists() and any(is_edl(p) for p in (JOBS / cand).glob("*_edl.json")):
        cand = f"{base}_{idx}"
        idx += 1
    return cand


def safe_file(job_dir, name):
    p = (job_dir / name).resolve()
    if job_dir.resolve() not in p.parents:
        raise ValueError("잘못된 파일 경로")
    return p


def read_json(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(p, data):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def _tts_say_plain(text):
    """shorts/edl.py 의 tts_say(plain(text)) 와 100% 동일한 정규화 (numpy/cv2 임포트 없이 실행)."""
    cleaned = re.sub(r"\[(\w+:)?|\]", "", str(text or ""))
    out = []
    for w in cleaned.split():
        w = SAY_MAP.get(w, w)
        w = re.sub(r"[ㄱ-ㅎㅏ-ㅣ;@~]+", "", w)
        if w.strip():
            out.append(w)
    return " ".join(out)


def _voice_md5_key(say_text):
    return hashlib.md5(say_text.strip().encode("utf-8")).hexdigest()[:16]


def capcut_tts_status(job_dir=None, edl_doc=None, cfg=None):
    """현재 설정(기본: CapCut '활기찬 바리톤' 1.1배속) 및 EDL 문장별 음성 준비 상태 점검."""
    cfg = cfg if cfg is not None else read_json(CONFIG, {})
    tcfg = copy_tts_cfg(cfg, edl_doc)
    provider = tcfg.get("provider", "capcut")
    cc_cfg = tcfg.get("capcut") or {}
    voice = cc_cfg.get("voice") or "vibrant_baritone"
    speed = float(cc_cfg.get("speed") or 1.1)
    vdir = ASSETS / "voices" / voice
    cached_files = len(list(vdir.glob("*.wav"))) if vdir.is_dir() else 0

    items_status = []
    missing = []
    if isinstance(edl_doc, dict):
        for idx, it in enumerate(edl_doc.get("items") or []):
            if it.get("type") != "narration":
                continue
            say = _tts_say_plain(it.get("text", ""))
            if not say:
                continue
            hkey = _voice_md5_key(say)
            ready = True if provider != "capcut" else (vdir / f"{hkey}.wav").is_file()
            entry = {"item": idx, "say": say, "hash": hkey, "ready": ready}
            items_status.append(entry)
            if not ready:
                missing.append(entry)

    has_draft = bool(job_dir and (job_dir / f"capcut_voice_{voice}.json").is_file())
    pending = read_json(CAPCUT_PENDING, []) or []
    return {
        "provider": provider,
        "voice": voice,
        "voice_ko": VOICE_KO_NAMES.get(voice, voice),
        "speed": speed,
        "cached_count": cached_files,
        "total_narr": len(items_status),
        "ready_narr": len(items_status) - len(missing),
        "items": items_status,
        "missing": missing,
        "has_voice_draft": has_draft,
        "capcut_pending_count": len(pending),
    }


def copy_tts_cfg(cfg, edl_doc=None):
    base = dict((cfg or {}).get("tts") or {})
    if isinstance(edl_doc, dict) and isinstance(edl_doc.get("tts"), dict):
        base = {**base, **edl_doc["tts"]}
    return base


def favorites_list():
    doc = read_json(FAVORITES, {}) or {}
    raw = doc.get("items", doc if isinstance(doc, list) else [])
    seen, out = set(), []
    for x in raw:
        nm = Path(str(x or "").split("/")[-1].strip()).stem
        if nm and nm.lower() not in seen:
            seen.add(nm.lower())
            out.append(nm)
    return out


def favorites_toggle(name, fav=None):
    clean = Path(str(name or "").split("/")[-1].strip()).stem
    if not clean:
        raise ValueError("효과음 이름이 비어 있습니다")
    cur = favorites_list()
    lower_map = {x.lower(): x for x in cur}
    exists = clean.lower() in lower_map
    want = (not exists) if fav is None else bool(fav)
    if want and not exists:
        cur.append(clean)
    elif not want and exists:
        cur = [x for x in cur if x.lower() != clean.lower()]
    write_json(FAVORITES, {"items": cur})
    return {"name": clean, "fav": want, "count": len(cur), "items": cur}


def is_edl(p):
    return p.suffix == ".json" and p.stem.endswith("_edl") and not p.name.startswith("preview_")


def parse_log(log_path, mix_report=None):
    """렌더 로그 + 자동 효과음 리포트 → 타임라인 재료."""
    items, shots, subs, sfx, notes = {}, [], [], [], []
    if not log_path.exists():
        return None
    for line in log_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if m := re.match(r"^item(\d+) \[(\w+)\] ([\d.]+)~([\d.]+)s", line):
            items[int(m[1])] = {"type": m[2], "a": float(m[3]), "b": float(m[4])}
        elif m := re.match(r"^item(\d+) shot(\d+): src ([\d.]+)~([\d.]+) → out ([\d.]+)~([\d.]+)\s*\((.*)\)", line):
            shots.append({"item": int(m[1]), "shot": int(m[2]), "src": float(m[3]),
                          "a": float(m[5]), "b": float(m[6]), "why": m[7]})
        elif m := re.match(r"^\s*\[최종 자막\] ([\d.]+)~([\d.]+) \([\d.]+s\): (.*)$", line):
            subs.append({"a": float(m[1]), "b": float(m[2]), "text": m[3]})
        elif line.startswith("효과음: "):
            for part in line[len("효과음: "):].split("; "):
                if m := re.match(r"^([\d.]+)s (\w+): (.*?) \(", part):
                    sfx.append({"t": float(m[1]), "cat": normalize_category(m[2]), "name": m[3]})
        elif m := re.match(r"^\s*([\d.]+)s\s+\[(\w+)\s*\]\s+(.+?)\s+\(피크보정", line):
            sfx.append({"t": float(m[1]), "cat": normalize_category(m[2]), "name": Path(m[3].strip()).stem})
        elif m := re.match(r"^\s*([\d.]+)s\s+(\w+)\s+(.+?)\s+음량\s+[+-]?[\d.]+dB", line):
            sfx.append({"t": float(m[1]), "cat": normalize_category(m[2]), "name": m[3].strip()})
        elif "⚠" in line or "❚" in line:
            notes.append(line.strip())

    if isinstance(mix_report, dict) and mix_report.get("resolved_cues"):
        sfx = [
            {
                "t": float(rc.get("cue", {}).get("timestamp_sec", 0.0)),
                "cat": normalize_category(rc.get("cue", {}).get("sfx_category", "pop")),
                "name": Path(rc.get("sfx", {}).get("file_name", "sfx")).stem,
                "db": rc.get("cue", {}).get("target_db"),
            }
            for rc in mix_report["resolved_cues"]
        ]

    for coll in (subs, sfx):
        for e in coll:
            t = e.get("t", e.get("a"))
            e["item"] = next((k for k, v in items.items() if v["a"] - 0.01 <= t < v["b"] - 0.01), None)
    return {"items": items, "shots": shots, "subs": subs, "sfx": sorted(sfx, key=lambda e: e["t"]), "notes": notes}


def video_info(job_dir, mp4):
    stem = mp4.stem
    meta = read_json(job_dir / f"{stem}_meta.json")
    if not meta:
        m = re.search(r"(v\d+[a-z]?)(?:_sfx\d+)?$", stem)
        guess = f"{m[1]}_edl.json" if m else f"{stem}_edl.json"
        meta = {"edl": guess if (job_dir / guess).exists() else None, "items": None, "guessed": True}
    mix_report = read_json(job_dir / f"{stem}_sfx_mix_report.json")
    log = parse_log(job_dir / f"{stem}_log.txt", mix_report=mix_report)
    if log and meta.get("items"):
        mp = meta["items"]
        re_i = lambda k: mp[k] if k is not None and k < len(mp) else None
        log["items"] = {re_i(k): v for k, v in log["items"].items() if re_i(k) is not None}
        for coll in (log["shots"], log["subs"], log["sfx"]):
            for e in coll:
                e["item"] = re_i(e["item"])
    return {
        "file": mp4.name,
        "mtime": mp4.stat().st_mtime,
        "size": mp4.stat().st_size,
        "edl": meta.get("edl"),
        "items": meta.get("items"),
        "draft": meta.get("draft", False),
        "duration": meta.get("duration"),
        "has_cuesheet": (job_dir / f"{stem}_sfx_cuesheet.json").is_file(),
        "sfx_base_video": meta.get("sfx_base_video"),
        "log": log,
    }


def next_version(job_dir):
    nums = [int(m[1]) for p in job_dir.glob("*_edl.json") if (m := re.match(r"^v(\d+)_edl$", p.stem))]
    return max(nums, default=0) + 1


def next_sfx_video_name(job_dir, base_video_name):
    base_stem = re.sub(r"_sfx\d+$", "", Path(base_video_name).stem)
    k = 1
    while (job_dir / f"{base_stem}_sfx{k}.mp4").exists():
        k += 1
    return f"{base_stem}_sfx{k}.mp4"


def _merged_sfx_map():
    """assets/sfx_catalog.json (2,869개 인덱서) 과 기존 assets/sfx_library.json 을 통합 반환."""
    by_cat = {c: {} for c in STANDARD_SFX_CATEGORIES}

    cat_doc = read_json(ASSETS / "sfx_catalog.json", {}) or {}
    for ent in (cat_doc.get("items") or cat_doc.get("entries") or []):
        fp = Path(ent.get("absolute_path", ""))
        if not fp.is_file() or ent.get("has_human_voice"):
            continue
        c = normalize_category(ent.get("category", "pop"))
        stem_name = Path(ent.get("file_name", fp.name)).stem
        by_cat.setdefault(c, {})[stem_name] = {
            "name": stem_name,
            "dur": round(float(ent.get("duration_sec", 0.0)), 2),
            "peak": round(float(ent.get("peak_offset_sec", 0.0)), 3),
            "desc": ent.get("description_ko", ""),
            "source": ent.get("source", "local"),
            "file": str(fp),
        }

    lib = read_json(ASSETS / "sfx_library.json", {}) or {}
    clap = read_json(ASSETS / "sfx_clap.json", {}) or {}
    for c, items in lib.items():
        nc = normalize_category(c)
        for it in items:
            if not clap.get(it.get("file", ""), {}).get("ok", True):
                continue
            fp = Path(it["file"])
            if not fp.is_file():
                continue
            nm = it["name"]
            by_cat.setdefault(nc, {}).setdefault(
                nm,
                {"name": nm, "dur": it.get("dur"), "peak": round(float(it.get("lead", 0.0)), 3),
                 "desc": "", "source": "sfxlib", "file": str(fp)},
            )
    return by_cat


def sfx_index():
    merged = _merged_sfx_map()
    fav_stems = load_favorite_stems(FAVORITES)
    is_fav = lambda nm: nm.lower() in fav_stems or re.sub(r"^\d+[._\-\s]+", "", nm.lower()) in fav_stems
    return {
        c: [
            {
                "name": v["name"],
                "dur": v["dur"],
                "peak": v["peak"],
                "desc": v["desc"],
                "source": v["source"],
                "fav": is_fav(v["name"]),
            }
            for v in sorted(
                items.values(),
                key=lambda x: (not is_fav(x["name"]), x["source"] == "repo_builtin", x["name"].lower()),
            )
        ]
        for c, items in merged.items()
        if items
    }


def sfx_file(cat, name):
    merged = _merged_sfx_map()
    nc = normalize_category(cat) if cat else ""
    if nc and name in merged.get(nc, {}):
        return Path(merged[nc][name]["file"])
    for items in merged.values():
        if name in items:
            return Path(items[name]["file"])
    return None


def director_status(cfg_dict=None):
    cfg_dict = cfg_dict if cfg_dict is not None else read_json(CONFIG, {})
    sfx_cfg = SFXConfig.from_env(ENV, repo_cfg=cfg_dict)
    cat_doc = read_json(ASSETS / "sfx_catalog.json", {}) or {}
    favs = favorites_list()
    pending = read_json(CAPCUT_PENDING, []) or []
    return {
        "auto_sfx_enabled": sfx_cfg.auto_sfx_enabled,
        "director_backend": sfx_cfg.director_backend,
        "resolved_backend": sfx_cfg.resolved_backend,
        "style_preset": sfx_cfg.style_preset,
        "style_presets": list(SFX_STYLE_PRESETS.values()),
        "favorites_count": len(favs),
        "capcut_pending_count": len(pending),
        "has_agy": bool(find_agy_cli()),
        "has_gemini_key": bool(sfx_cfg.gemini_api_key),
        "acquisition_mode": sfx_cfg.acquisition_mode,
        "catalog_count": len(cat_doc.get("items") or cat_doc.get("entries") or []),
    }


def env_read():
    vals = {}
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                vals[k.strip()] = v.strip().strip('"').strip("'")
    return vals


def env_write(updates):
    lines = ENV.read_text(encoding="utf-8").splitlines() if ENV.exists() else []
    done = set()
    for i, line in enumerate(lines):
        k = line.split("=", 1)[0].strip()
        if "=" in line and not line.strip().startswith("#") and k in updates:
            lines[i] = f"{k}={updates[k]}"
            done.add(k)
    lines += [f"{k}={v}" for k, v in updates.items() if k not in done]
    ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")


def which(cmd):
    from shutil import which as w
    return bool(w(cmd))


def has_py_mod(mod_name: str) -> bool:
    try:
        return importlib.util.find_spec(mod_name) is not None
    except Exception:
        return False


# ---------------------------------------------------------------- HTTP
class H(BaseHTTPRequestHandler):
    server_version = "ShortsEditor/0.6"

    def log_message(self, *a):
        pass

    def send_json(self, data, code=200):
        b = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def send_file(self, p, ctype=None):
        p = Path(p)
        if not p.is_file():
            return self.send_json({"error": "파일 없음"}, 404)
        size = p.stat().st_size
        ctype = ctype or mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        rng = self.headers.get("Range")
        a, b = 0, size - 1
        if rng and (m := re.match(r"bytes=(\d*)-(\d*)", rng)):
            if m[1]:
                a = int(m[1])
                b = int(m[2]) if m[2] else size - 1
            else:
                a = size - int(m[2])
            b = min(b, size - 1)
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {a}-{b}/{size}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(b - a + 1))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        with open(p, "rb") as f:
            f.seek(a)
            left = b - a + 1
            try:
                while left > 0:
                    chunk = f.read(min(1 << 16, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n).decode("utf-8") or "{}")

    def do_GET(self):
        try:
            self.route_get()
        except FileNotFoundError as e:
            self.send_json({"error": f"없음: {e}"}, 404)
        except Exception as e:
            self.send_json({"error": str(e)}, 400)

    def do_POST(self):
        try:
            self.route_post()
        except Exception as e:
            self.send_json({"error": str(e)}, 400)

    # ---- GET
    def route_get(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        path = unquote(u.path)

        if path == "/" or path.startswith("/static/"):
            f = STATIC / ("index.html" if path == "/" else path[len("/static/"):])
            if STATIC.resolve() not in f.resolve().parents:
                return self.send_json({"error": "없음"}, 404)
            return self.send_file(f)

        if path == "/api/jobs":
            jobs = []
            if JOBS.is_dir():
                for d in sorted(JOBS.iterdir(), key=lambda p: -p.stat().st_mtime):
                    if d.is_dir() and not d.name.startswith((".", "_")):
                        edls = [p for p in d.glob("*_edl.json") if is_edl(p)]
                        vids = list(d.glob("*.mp4"))
                        if edls:
                            jobs.append({"name": d.name, "edls": len(edls), "videos": len(vids),
                                         "mtime": max(p.stat().st_mtime for p in edls)})
            return self.send_json(jobs)

        if path == "/api/job":
            jd = safe_job(q.get("job"))
            edls = sorted([p for p in jd.glob("*_edl.json") if is_edl(p)], key=lambda p: -p.stat().st_mtime)
            vids = sorted([p for p in jd.glob("*.mp4") if p.name != "source.mp4"], key=lambda p: -p.stat().st_mtime)
            broll = sorted(p.relative_to(jd).as_posix() for p in (jd / "broll").glob("*.mp4")) if (jd / "broll").is_dir() else []
            tr = read_json(jd / "transcript.json", []) or []
            first_edl = read_json(edls[0]) if edls else None
            return self.send_json({
                "name": jd.name,
                "edls": [{"file": p.name, "mtime": p.stat().st_mtime} for p in edls],
                "videos": [video_info(jd, p) for p in vids],
                "broll": broll,
                "transcript": {str(r["id"]): {"start": r["start"], "end": r["end"], "text": r["text"]} for r in tr},
                "words": {k: [w["w"] for w in v] for k, v in (read_json(jd / "transcript_words.json", {}) or {}).items()},
                "has_source": (jd / "source.mp4").exists(),
                "director": director_status(),
                "tts": capcut_tts_status(jd, first_edl),
            })

        if path == "/api/edl":
            jd = safe_job(q.get("job"))
            return self.send_json(read_json(safe_file(jd, q["file"])))

        if path == "/api/tts/status":
            jd = safe_job(q.get("job")) if q.get("job") else None
            edl_doc = read_json(safe_file(jd, q["file"])) if (jd and q.get("file")) else None
            return self.send_json(capcut_tts_status(jd, edl_doc))

        if path == "/api/cuesheet":
            jd = safe_job(q.get("job"))
            vid_name = q.get("video", "")
            if not vid_name:
                return self.send_json({"exists": False, "cuesheet": None, "mix_report": None, "status": director_status()})
            vid_p = safe_file(jd, vid_name)
            stem = vid_p.stem
            cue_p = jd / f"{stem}_sfx_cuesheet.json"
            if not cue_p.is_file():
                base_stem = re.sub(r"_sfx\d+$", "", stem)
                alt = jd / f"{base_stem}_sfx_cuesheet.json"
                if alt.is_file():
                    cue_p = alt
            sheet = read_json(cue_p) if cue_p.is_file() else None
            rep = read_json(jd / f"{stem}_sfx_mix_report.json")
            return self.send_json({
                "exists": sheet is not None,
                "cuesheet_file": cue_p.name if sheet is not None else f"{stem}_sfx_cuesheet.json",
                "cuesheet": sheet,
                "mix_report": rep,
                "status": director_status(),
            })

        if path == "/api/sfx/presets":
            return self.send_json(list(SFX_STYLE_PRESETS.values()))

        if path == "/api/sfx/favorites":
            items = favorites_list()
            return self.send_json({"items": items, "count": len(items)})

        if path == "/api/frame":
            jd = safe_job(q.get("job"))
            src = safe_file(jd, q.get("file") or "source.mp4")
            t = max(0.0, float(q.get("t", 0)))
            cache = jd / "edl_tmp" / "frames"
            cache.mkdir(parents=True, exist_ok=True)
            out = cache / f"{src.stem}_{t:.2f}.jpg"
            if not out.exists():
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(src), "-frames:v", "1",
                                "-vf", "scale=320:-2", "-q:v", "4", str(out)], capture_output=True)
            return self.send_file(out, "image/jpeg")

        if path.startswith("/media/"):
            _, _, job, *rest = path.split("/")
            jd = safe_job(job)
            return self.send_file(safe_file(jd, "/".join(rest)))

        if path == "/api/sfx":
            return self.send_json(sfx_index())

        if path == "/sfx":
            f = sfx_file(q.get("cat", ""), q.get("name", ""))
            return self.send_file(f) if f else self.send_json({"error": "없음"}, 404)

        if path == "/api/presets":
            return self.send_json([{"id": p.stem, **read_json(p, {})} for p in sorted(PRESETS.glob("*.json"))])

        if path == "/api/task":
            return self.send_json({k: TASK[k] for k in ("kind", "running", "out", "job", "ok", "started")}
                                  | {"log": TASK["log"][-60:]})

        if path == "/api/settings":
            env = env_read()
            cfg = read_json(CONFIG, {})
            sfx_dir = env.get("LOCAL_SFX_DIR") or cfg.get("auto_sfx", {}).get("local_sfx_dir") or cfg.get("sfx_library", {}).get("dir", "")
            d_stat = director_status(cfg)
            t_stat = capcut_tts_status(cfg=cfg)
            return self.send_json({
                "keys": {k: bool(env.get(k)) for k in KEY_NAMES},
                "sfx_dir": sfx_dir,
                "sfx_dir_ok": bool(sfx_dir) and Path(sfx_dir).is_dir(),
                "sfx_count": sum(len(v) for v in sfx_index().values()),
                "director": d_stat,
                "tts_provider": cfg.get("tts", {}).get("provider", "capcut"),
                "capcut_voice": cfg.get("tts", {}).get("capcut", {}).get("voice", "vibrant_baritone"),
                "capcut_speed": cfg.get("tts", {}).get("capcut", {}).get("speed", 1.1),
                "tts_status": t_stat,
                "voice_id": cfg.get("tts", {}).get("typecast", {}).get("voice_id", ""),
                "jobs_dir": str(JOBS),
                "tools": {
                    "ffmpeg": which("ffmpeg"),
                    "ffprobe": which("ffprobe"),
                    "yt_dlp": which("yt-dlp") or has_py_mod("yt_dlp"),
                    "faster_whisper": has_py_mod("faster_whisper"),
                    "agy": d_stat["has_agy"],
                    "whisperx": (ROOT / cfg.get("align", {}).get("python", ".venv-whisperx/Scripts/python.exe")).exists(),
                },
            })

        self.send_json({"error": "없는 주소"}, 404)

    # ---- POST
    def route_post(self):
        path = urlparse(self.path).path
        d = self.body()

        if path == "/api/jobs/create":
            src = str(d.get("src") or "").strip()
            if not src:
                raise ValueError("유튜브 URL 또는 로컬 동영상 경로를 입력해 주세요.")
            is_url = bool(re.match(r"^https?://", src, re.I))
            if not is_url and not Path(src).is_file():
                raise ValueError("유효한 유튜브 주소(https://...) 또는 존재하는 로컬 동영상 파일 경로를 입력해 주세요.")

            title_hint = str(d.get("title_hint") or "").strip()
            context = str(d.get("context") or "").strip()
            job_name = suggest_job_name(d.get("name") or "", title_hint, src)
            script_mode = str(d.get("script_mode") or "auto").strip().lower()
            if script_mode not in ("auto", "claude-cli", "agy-cli", "claude", "gemini", "openai", "starter"):
                script_mode = "auto"

            cmd = [
                sys.executable,
                "-u",
                str(HERE / "new_job_worker.py"),
                "--name",
                job_name,
                "--src",
                src,
                "--script-mode",
                script_mode,
            ]
            if title_hint:
                cmd += ["--title-hint", title_hint]
            if context:
                cmd += ["--context", context]
            if d.get("start") not in (None, ""):
                cmd += ["--start", str(float(d["start"]))]
            if d.get("end") not in (None, ""):
                cmd += ["--end", str(float(d["end"]))]

            ok = start_task("new_job", cmd, job=job_name, out="v1_edl.json")
            return self.send_json(
                {"started": ok, "job": job_name, "edl": "v1_edl.json"} if ok else {"error": "이미 다른 작업이 진행 중입니다"},
                200 if ok else 409,
            )

        if path == "/api/edl/save":
            jd = safe_job(d["job"])
            name = f"v{next_version(jd)}_edl.json"
            write_json(jd / name, d["edl"])
            return self.send_json({"file": name})

        if path == "/api/sfx/favorite":
            res = favorites_toggle(d.get("name"), d.get("fav"))
            return self.send_json(res)

        if path == "/api/tts/status":
            jd = safe_job(d["job"]) if d.get("job") else None
            return self.send_json(capcut_tts_status(jd, d.get("edl")))

        if path == "/api/tts/capcut/make":
            jd = safe_job(d["job"])
            edl_file = d.get("edl_file") or ""
            safe_file(jd, edl_file)
            cfg = read_json(CONFIG, {})
            voice = (d.get("voice") or cfg.get("tts", {}).get("capcut", {}).get("voice") or "vibrant_baritone").strip()
            cmd = [
                sys.executable, "-u", str(ROOT / "tools" / "capcut_voice.py"), "make",
                "--job", jd.name, "--edl", edl_file, "--voice", voice,
            ]
            ok = start_task("tts_make", cmd, job=jd.name, out=f"voice_{jd.name}_{voice}")
            return self.send_json({"started": ok, "voice": voice} if ok else {"error": "이미 다른 작업이 진행 중입니다"},
                                  200 if ok else 409)

        if path == "/api/tts/capcut/harvest":
            jd = safe_job(d["job"])
            cfg = read_json(CONFIG, {})
            cc_cfg = cfg.get("tts", {}).get("capcut", {})
            voice = (d.get("voice") or cc_cfg.get("voice") or "vibrant_baritone").strip()
            fb_speed = float(d.get("fallback_speed", cc_cfg.get("speed", 1.1)))
            cmd = [
                sys.executable, "-u", str(ROOT / "tools" / "capcut_voice.py"), "harvest",
                "--job", jd.name, "--voice", voice, "--fallback-speed", str(fb_speed),
            ]
            ok = start_task("tts_harvest", cmd, job=jd.name, out=voice)
            return self.send_json({"started": ok, "voice": voice} if ok else {"error": "이미 다른 작업이 진행 중입니다"},
                                  200 if ok else 409)

        if path == "/api/capcut/export":
            jd = safe_job(d["job"])
            edl_file = d["edl_file"]
            safe_file(jd, edl_file)
            stem = Path(edl_file).stem.removesuffix("_edl")
            proj_name = d.get("name") or f"{jd.name}_{stem}"
            cmd = [
                sys.executable, "-u", "-m", "shorts.capcut",
                "--job", jd.name,
                "--edl", edl_file,
                "--fast-if-ready",
            ]
            if d.get("preset"):
                cmd += ["--preset", d["preset"]]
            if d.get("video"):
                safe_file(jd, d["video"])
                cmd += ["--sfx-video", d["video"]]
            if d.get("name"):
                cmd += ["--name", d["name"]]
            ok = start_task("capcut_export", cmd, job=jd.name, out=proj_name)
            return self.send_json({"started": ok, "project": proj_name} if ok else {"error": "이미 다른 작업이 진행 중입니다"},
                                  200 if ok else 409)

        if path == "/api/capcut/register":
            cmd = [sys.executable, "-u", "-m", "shorts.capcut", "--register-only"]
            ok = start_task("capcut_reg", cmd, out="CapCut 목록 등록")
            return self.send_json({"started": ok} if ok else {"error": "이미 다른 작업이 진행 중입니다"},
                                  200 if ok else 409)

        if path == "/api/render":
            jd = safe_job(d["job"])
            items = [int(i) for i in d.get("items") or []]
            if d.get("draft"):
                if not items:
                    raise ValueError("저장하지 않은 내용은 박자 미리보기만 됩니다. 전체 렌더링은 새 버전으로 저장한 뒤에 합니다.")
                (jd / "edl_tmp").mkdir(exist_ok=True)
                write_json(jd / "edl_tmp" / "draft_edl.json", d["draft"])
                edl, base = "edl_tmp/draft_edl.json", "draft"
            else:
                edl = d["edl_file"]
                safe_file(jd, edl)
                m = re.match(r"^(v\d+)_edl$", Path(edl).stem)
                base = m[1] if m else Path(edl).stem.replace("_edl", "")
            if items:
                out = f"preview_{base}_b{'-'.join(str(i + 1) for i in items[:4])}.mp4"
            else:
                out = f"full_{base}.mp4"
                k = 2
                while (jd / out).exists():
                    out = f"full_{base}_{k}.mp4"
                    k += 1
            cmd = [sys.executable, "-u", str(HERE / "render_worker.py"), "--job", jd.name, "--edl", edl, "--out", out]
            if items:
                cmd += ["--items", ",".join(map(str, items))]
            if d.get("preset"):
                cmd += ["--preset", d["preset"]]
            ok = start_task("render", cmd, job=jd.name, out=out)
            return self.send_json({"started": ok, "out": out} if ok else {"error": "이미 다른 작업이 진행 중입니다"},
                                  200 if ok else 409)

        if path == "/api/cuesheet/generate":
            jd = safe_job(d["job"])
            vid_p = safe_file(jd, d["video"])
            edl_file = d.get("edl_file") or ""
            edl_p = safe_file(jd, edl_file) if edl_file and (jd / edl_file).is_file() else None
            cfg = read_json(CONFIG, {})
            sfx_cfg = SFXConfig.from_env(ENV, repo_cfg=cfg)
            style_preset = normalize_style_preset(d.get("style_preset") or sfx_cfg.style_preset)
            sfx_cfg = sfx_cfg.with_style_preset(style_preset)
            req_backend = (d.get("backend") or sfx_cfg.director_backend or "auto").strip().lower()
            effective = req_backend
            if effective == "auto":
                effective = sfx_cfg.resolved_backend

            if effective == "local-free":
                sfx_cfg.gemini_api_key = ""
                log_p = jd / f"{vid_p.stem}_log.txt"
                if not log_p.is_file():
                    meta = read_json(jd / f"{vid_p.stem}_meta.json") or {}
                    bv = meta.get("sfx_base_video")
                    if bv and (jd / f"{Path(bv).stem}_log.txt").is_file():
                        log_p = jd / f"{Path(bv).stem}_log.txt"
                subs, exp_items = parse_companion_log(log_p)
                hints = extract_edl_hints(edl_p, exp_items)
                out_json = jd / f"{vid_p.stem}_sfx_cuesheet.json"
                sheet = generate_sfx_cuesheet(
                    video_path=vid_p,
                    config=sfx_cfg,
                    output_json_path=out_json,
                    edl_hints=hints,
                    edl_sub_list=subs or None,
                    edl_items=exp_items or None,
                    backend_override="local-free",
                    style_preset=style_preset,
                )
                return self.send_json({"started": False, "sync": True, "style_preset": style_preset, "cuesheet": sheet.to_dict()})

            cmd = [
                sys.executable, "-u", str(HERE / "sfx_worker.py"), "generate",
                "--job", jd.name, "--video", vid_p.name, "--backend", effective, "--style-preset", style_preset,
            ]
            if edl_p:
                cmd += ["--edl", edl_p.name]
            ok = start_task("cuesheet", cmd, job=jd.name, out=vid_p.name)
            return self.send_json({"started": ok, "sync": False, "style_preset": style_preset, "video": vid_p.name} if ok else {"error": "이미 다른 작업이 진행 중입니다"},
                                  200 if ok else 409)

        if path == "/api/cuesheet/save":
            jd = safe_job(d["job"])
            vid_p = safe_file(jd, d["video"])
            raw_sheet = d.get("cuesheet") or {}
            cues = []
            for idx, c in enumerate(raw_sheet.get("cues") or [], 1):
                ts = max(0.0, float(c.get("timestamp_sec", 0.0)))
                cues.append({
                    **c,
                    "cue_id": c.get("cue_id") or f"cue_{idx:02d}",
                    "timestamp_sec": round(ts, 3),
                    "timestamp": format_mmss(ts),
                    "sfx_category": normalize_category(c.get("sfx_category", "pop")),
                    "target_db": round(max(-24.0, min(-6.0, float(c.get("target_db", -15.0)))), 1),
                    "duck_under_speech": bool(c.get("duck_under_speech", True)),
                    "pinned_name": str(c.get("pinned_name") or "").strip(),
                })
            cues.sort(key=lambda x: x["timestamp_sec"])
            raw_sheet["cues"] = cues
            sheet = SFXCuesheet.from_dict(raw_sheet)
            out_p = jd / f"{vid_p.stem}_sfx_cuesheet.json"
            out_p.write_text(json.dumps(sheet.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
            return self.send_json({"saved": True, "file": out_p.name, "cuesheet": sheet.to_dict()})

        if path == "/api/cuesheet/apply":
            jd = safe_job(d["job"])
            vid_p = safe_file(jd, d["video"])
            cue_p = jd / f"{vid_p.stem}_sfx_cuesheet.json"
            if d.get("cuesheet"):
                raw_sheet = d["cuesheet"]
                for idx, c in enumerate(raw_sheet.get("cues") or [], 1):
                    ts = max(0.0, float(c.get("timestamp_sec", 0.0)))
                    c["cue_id"] = c.get("cue_id") or f"cue_{idx:02d}"
                    c["timestamp_sec"] = round(ts, 3)
                    c["timestamp"] = format_mmss(ts)
                    c["sfx_category"] = normalize_category(c.get("sfx_category", "pop"))
                    c["target_db"] = round(max(-24.0, min(-6.0, float(c.get("target_db", -15.0)))), 1)
                raw_sheet["cues"] = sorted(raw_sheet.get("cues") or [], key=lambda x: x["timestamp_sec"])
                sheet = SFXCuesheet.from_dict(raw_sheet)
                cue_p.write_text(json.dumps(sheet.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
            if not cue_p.is_file():
                raise ValueError("먼저 큐시트를 생성하거나 효과음을 추가해 주세요.")

            meta = read_json(jd / f"{vid_p.stem}_meta.json") or {}
            base_vid_name = meta.get("sfx_base_video") or vid_p.name
            if not (jd / base_vid_name).is_file():
                base_vid_name = vid_p.name
            out_name = next_sfx_video_name(jd, base_vid_name)
            edl_file = d.get("edl_file") or meta.get("edl") or ""

            cmd = [
                sys.executable, "-u", str(HERE / "sfx_worker.py"), "apply",
                "--job", jd.name,
                "--base-video", base_vid_name,
                "--cuesheet", cue_p.name,
                "--out", out_name,
            ]
            if edl_file:
                cmd += ["--edl", edl_file]
            ok = start_task("sfx_remix", cmd, job=jd.name, out=out_name)
            return self.send_json({"started": ok, "out": out_name} if ok else {"error": "이미 다른 작업이 진행 중입니다"},
                                  200 if ok else 409)

        if path == "/api/settings":
            env_updates = {k: v.strip() for k, v in (d.get("keys") or {}).items() if k in KEY_NAMES and v and v.strip()}
            cfg = read_json(CONFIG, {})
            cfg_changed = False

            if d.get("sfx_dir") is not None:
                clean_dir = d["sfx_dir"].strip().replace("\\", "/")
                cfg.setdefault("sfx_library", {})["dir"] = clean_dir
                cfg.setdefault("auto_sfx", {})["local_sfx_dir"] = clean_dir
                if clean_dir:
                    env_updates["LOCAL_SFX_DIR"] = d["sfx_dir"].strip()
                cfg_changed = True
            if d.get("tts_provider"):
                prov = str(d["tts_provider"]).strip().lower()
                if prov in ("capcut", "typecast", "fish", "sapi"):
                    cfg.setdefault("tts", {})["provider"] = prov
                    cfg_changed = True
            if d.get("capcut_voice"):
                cfg.setdefault("tts", {}).setdefault("capcut", {})["voice"] = str(d["capcut_voice"]).strip()
                cfg_changed = True
            if d.get("capcut_speed") is not None:
                cfg.setdefault("tts", {}).setdefault("capcut", {})["speed"] = round(max(0.7, min(1.6, float(d["capcut_speed"]))), 2)
                cfg_changed = True
            if d.get("voice_id") is not None and d["voice_id"].strip():
                cfg.setdefault("tts", {}).setdefault("typecast", {})["voice_id"] = d["voice_id"].strip()
                cfg_changed = True
            if d.get("auto_sfx_enabled") is not None:
                on = bool(d["auto_sfx_enabled"])
                cfg.setdefault("auto_sfx", {})["enabled"] = on
                env_updates["AUTO_SFX_ENABLED"] = "true" if on else "false"
                cfg_changed = True
            if d.get("director_backend"):
                b_mode = str(d["director_backend"]).strip().lower()
                if b_mode in ("auto", "local-free", "agy-cli", "gemini-api"):
                    cfg.setdefault("auto_sfx", {})["director_backend"] = b_mode
                    env_updates["SFX_DIRECTOR_BACKEND"] = b_mode
                    cfg_changed = True
            if d.get("style_preset"):
                s_preset = normalize_style_preset(d["style_preset"])
                cfg.setdefault("auto_sfx", {})["style_preset"] = s_preset
                env_updates["SFX_STYLE_PRESET"] = s_preset
                cfg_changed = True

            if env_updates:
                env_write(env_updates)
                for k, v in env_updates.items():
                    os.environ[k] = v
            if cfg_changed:
                CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
            saved_keys = [k for k in env_updates if k in KEY_NAMES]
            return self.send_json({"saved": sorted(saved_keys), "director": director_status(cfg), "tts": capcut_tts_status(cfg=cfg)})

        if path == "/api/sfx/reindex":
            mode = str(d.get("mode") or "free").strip().lower()
            if mode not in ("free", "gemini-free-tier", "gemini"):
                mode = "free"
            cmd = [sys.executable, "-u", str(HERE / "sfx_worker.py"), "index", "--mode", mode]
            ok = start_task("sfx_index", cmd)
            return self.send_json({"started": ok, "mode": mode} if ok else {"error": "이미 다른 작업이 진행 중입니다"},
                                  200 if ok else 409)

        self.send_json({"error": "없는 주소"}, 404)


def main():
    srv = None
    for port in range(PORT, PORT + 20):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", port), H)
            break
        except OSError:
            continue
    if srv is None:
        sys.exit("빈 포트를 찾지 못했습니다")
    url = f"http://127.0.0.1:{port}"
    print(f"쇼츠 편집기: {url}  (끄려면 Ctrl+C)")
    if "--no-browser" not in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
