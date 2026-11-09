"""쇼츠 편집기 서버 (파이썬 기본 라이브러리만 사용, 이 컴퓨터에서만 접속 가능).

실행: python editor/server.py   →  http://127.0.0.1:8765
"""
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
from shorts.common import ASSETS, JOBS  # noqa: E402

STATIC = HERE / "static"
PRESETS = HERE / "presets"
ENV = ROOT / ".env"
CONFIG = ROOT / "config.json"
PORT = int(os.environ.get("EDITOR_PORT", "47615"))
KEY_NAMES = ["TYPECAST_API_KEY", "FISH_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"]
NAME_RE = re.compile(r"^[^/\\:*?\"<>|]+$")

# ---------------------------------------------------------------- 작업(렌더·색인) 한 번에 하나
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
    Path(p).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def is_edl(p):
    return p.suffix == ".json" and p.stem.endswith("_edl") and not p.name.startswith("preview_")


def parse_log(log_path):
    """렌더 로그 → 타임라인 재료.
    item3 [clip] 5.30~7.67s / item0 shot1: src 89.62~90.52 → out 0.87~1.77  (why)
    [최종 자막] 0.00~0.87 (0.87s): 텍스트 / 효과음: 0.00s ding: Ting (...); ..."""
    items, shots, subs, sfx, notes = {}, [], [], [], []
    if not log_path.exists():
        return None
    for line in log_path.read_text(encoding="utf-8").splitlines():
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
                    sfx.append({"t": float(m[1]), "cat": m[2], "name": m[3]})
        elif "⚠" in line or "❚" in line:
            notes.append(line.strip())
    for coll in (subs, sfx):  # 시간으로 어느 박자인지
        for e in coll:
            t = e.get("t", e.get("a"))
            e["item"] = next((k for k, v in items.items() if v["a"] - 0.01 <= t < v["b"] - 0.01), None)
    return {"items": items, "shots": shots, "subs": subs, "sfx": sorted(sfx, key=lambda e: e["t"]), "notes": notes}


def video_info(job_dir, mp4):
    stem = mp4.stem
    meta = read_json(job_dir / f"{stem}_meta.json")
    if not meta:  # 편집기 이전에 만든 영상: full_v5.mp4 ↔ v5_edl.json 처럼 이름으로 추정
        m = re.search(r"(v\d+[a-z]?)$", stem)
        guess = f"{m[1]}_edl.json" if m else f"{stem}_edl.json"
        meta = {"edl": guess if (job_dir / guess).exists() else None, "items": None, "guessed": True}
    log = parse_log(job_dir / f"{stem}_log.txt")
    if log and meta.get("items"):  # 일부 박자만 렌더한 미리보기 → 원래 박자 번호로
        mp = meta["items"]
        re_i = lambda k: mp[k] if k is not None and k < len(mp) else None
        log["items"] = {re_i(k): v for k, v in log["items"].items() if re_i(k) is not None}
        for coll in (log["shots"], log["subs"], log["sfx"]):
            for e in coll:
                e["item"] = re_i(e["item"])
    return {"file": mp4.name, "mtime": mp4.stat().st_mtime, "size": mp4.stat().st_size,
            "edl": meta.get("edl"), "items": meta.get("items"), "draft": meta.get("draft", False),
            "duration": meta.get("duration"), "log": log}


def next_version(job_dir):
    nums = [int(m[1]) for p in job_dir.glob("*_edl.json") if (m := re.match(r"^v(\d+)_edl$", p.stem))]
    return max(nums, default=0) + 1


def sfx_index():
    lib = read_json(ASSETS / "sfx_library.json", {}) or {}
    clap = read_json(ASSETS / "sfx_clap.json", {}) or {}
    return {c: [{"name": it["name"], "dur": it.get("dur")} for it in items
                if clap.get(it["file"], {}).get("ok", True)] for c, items in lib.items()}


def sfx_file(cat, name):
    for it in (read_json(ASSETS / "sfx_library.json", {}) or {}).get(cat, []):
        if it["name"] == name:
            return Path(it["file"])
    return None


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


# ---------------------------------------------------------------- HTTP
class H(BaseHTTPRequestHandler):
    server_version = "ShortsEditor/0.1"

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
            return self.send_json({
                "name": jd.name,
                "edls": [{"file": p.name, "mtime": p.stat().st_mtime} for p in edls],
                "videos": [video_info(jd, p) for p in vids],
                "broll": broll,
                "transcript": {str(r["id"]): {"start": r["start"], "end": r["end"], "text": r["text"]} for r in tr},
                "words": {k: [w["w"] for w in v] for k, v in (read_json(jd / "transcript_words.json", {}) or {}).items()},
                "has_source": (jd / "source.mp4").exists(),
            })

        if path == "/api/edl":
            jd = safe_job(q.get("job"))
            return self.send_json(read_json(safe_file(jd, q["file"])))

        if path == "/api/frame":  # 장면 썸네일: 원본(또는 B-roll)의 t초 프레임
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
            sfx_dir = cfg.get("sfx_library", {}).get("dir", "")
            return self.send_json({
                "keys": {k: bool(env.get(k)) for k in KEY_NAMES},
                "sfx_dir": sfx_dir,
                "sfx_dir_ok": bool(sfx_dir) and Path(sfx_dir).is_dir(),
                "sfx_count": sum(len(v) for v in sfx_index().values()),
                "tts_provider": cfg.get("tts", {}).get("provider"),
                "voice_id": cfg.get("tts", {}).get("typecast", {}).get("voice_id", ""),
                "jobs_dir": str(JOBS),
                "tools": {"ffmpeg": which("ffmpeg"), "ffprobe": which("ffprobe"),
                          "whisperx": (ROOT / cfg.get("align", {}).get("python", ".venv-whisperx/Scripts/python.exe")).exists()},
            })

        self.send_json({"error": "없는 주소"}, 404)

    # ---- POST
    def route_post(self):
        path = urlparse(self.path).path
        d = self.body()

        if path == "/api/edl/save":  # 항상 새 버전 파일로 저장 (기존 파일은 그대로)
            jd = safe_job(d["job"])
            name = f"v{next_version(jd)}_edl.json"
            write_json(jd / name, d["edl"])
            return self.send_json({"file": name})

        if path == "/api/render":
            jd = safe_job(d["job"])
            items = [int(i) for i in d.get("items") or []]
            if d.get("draft"):  # 저장 전 편집 내용으로 박자 미리보기
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
                while (jd / out).exists():  # 이미 있는 완성본은 덮어쓰지 않음
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

        if path == "/api/settings":
            keys = {k: v.strip() for k, v in (d.get("keys") or {}).items() if k in KEY_NAMES and v and v.strip()}
            if keys:
                env_write(keys)
            if d.get("sfx_dir") is not None or d.get("voice_id") is not None:
                cfg = read_json(CONFIG, {})
                if d.get("sfx_dir") is not None:
                    cfg.setdefault("sfx_library", {})["dir"] = d["sfx_dir"].strip().replace("\\", "/")
                if d.get("voice_id"):
                    cfg.setdefault("tts", {}).setdefault("typecast", {})["voice_id"] = d["voice_id"].strip()
                CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            return self.send_json({"saved": sorted(keys)})

        if path == "/api/sfx/reindex":
            ok = start_task("sfx_index", [sys.executable, "-u", "-m", "shorts.sfxlib"])
            return self.send_json({"started": ok} if ok else {"error": "이미 다른 작업이 진행 중입니다"},
                                  200 if ok else 409)

        self.send_json({"error": "없는 주소"}, 404)


def main():
    srv = None
    for port in range(PORT, PORT + 20):  # 다른 프로그램이 쓰는 포트면 다음 번호로
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
