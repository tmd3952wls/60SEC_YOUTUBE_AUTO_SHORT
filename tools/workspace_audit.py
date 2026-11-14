"""Workspace-only audit & 15-reference YouTube Shorts decomposition tool.

Strictly operates within repository root (`jobs/`, `assets/`, `ext/`, `.venv*`).
"""
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
from scipy.signal import fftconvolve

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT_DIR = ROOT / "jobs" / "_ref15"
OUT_DIR.mkdir(parents=True, exist_ok=True)

REF_IDS = [
    "YVBql8gjaUg",
    "QMJtjJz4M6w",
    "2jJoIbdciDY",
    "kmQGQNJgSVo",
    "h00vdwsFphw",
    "vbxJ_v132ao",
    "hZgCO9PEnO8",
    "uRYpcMENqfo",
    "R9UCbQRLQBc",
    "aFqKN8s2cA8",
    "wqAgBL7ODok",
    "mVzrvBpMu3E",
    "r0LYu7MgCc8",
    "CDvW0OUR22I",
    "0HbV-PW3ivw",
]


def audit_workspace():
    info = {
        "venvs": {},
        "main_python_pkgs": "",
        "ext_dirs": [],
        "voices": {},
        "existing_ref_files": [],
        "jobs": {},
        "circles_in_edls": [],
    }

    for vp in sorted(ROOT.glob(".venv*")):
        py = vp / "Scripts" / "python.exe"
        pkgs = ""
        if py.is_file():
            r = subprocess.run(
                [str(py), "-c", "import importlib.util as u; print([m for m in ['whisperx','demucs','torch','torchaudio','TTS','edge_tts','librosa'] if u.find_spec(m)])"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            pkgs = r.stdout.strip()
        info["venvs"][vp.name] = {"python": str(py.relative_to(ROOT)) if py.is_file() else None, "pkgs": pkgs}

    r_main = subprocess.run(
        [sys.executable, "-c", "import importlib.util as u; print([m for m in ['faster_whisper','whisperx','demucs','torch','librosa','edge_tts','yt_dlp','scipy','cv2'] if u.find_spec(m)])"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    info["main_python_pkgs"] = r_main.stdout.strip()

    if (ROOT / "ext").is_dir():
        info["ext_dirs"] = sorted(p.name for p in (ROOT / "ext").iterdir())

    voices_dir = ROOT / "assets" / "voices"
    if voices_dir.is_dir():
        for vd in sorted(p for p in voices_dir.iterdir() if p.is_dir()):
            wavs = []
            for w in sorted(vd.glob("*.wav")):
                d_str = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(w)],
                    capture_output=True, text=True,
                ).stdout.strip()
                wavs.append({"file": w.name, "dur": round(float(d_str or 0), 2), "bytes": w.stat().st_size})
            info["voices"][vd.name] = wavs

    for p in ROOT.rglob("*"):
        if p.is_file() and OUT_DIR not in p.parents:
            if any(rid in p.name for rid in REF_IDS) or ("ref" in p.name.lower() and p.suffix.lower() in {".json", ".mp4", ".wav", ".md"}):
                info["existing_ref_files"].append(p.relative_to(ROOT).as_posix())

    jobs_dir = ROOT / "jobs"
    if jobs_dir.is_dir():
        for jd in sorted(p for p in jobs_dir.iterdir() if p.is_dir() and not p.name.startswith("_")):
            edls = sorted(jd.glob("*_edl.json"))
            latest = None
            for ep in edls:
                try:
                    edoc = json.loads(ep.read_text(encoding="utf-8"))
                    items = edoc.get("items") or []
                    shots_cnt = sum(len(it.get("shots") or []) for it in items)
                    for it in items:
                        for sh in (it.get("shots") or []):
                            if sh.get("circle"):
                                info["circles_in_edls"].append({
                                    "job": jd.name,
                                    "edl": ep.name,
                                    "crop": sh.get("crop"),
                                    "circle": sh["circle"],
                                })
                    latest = {
                        "edl": ep.name,
                        "title": [x.get("text") for x in (edoc.get("title_lines") or [])],
                        "items": len(items),
                        "shots": shots_cnt,
                    }
                except Exception:
                    pass
            info["jobs"][jd.name] = {
                "has_source": (jd / "source.mp4").is_file(),
                "has_source_vocals": (jd / "source_vocals.wav").is_file(),
                "broll_count": len(list((jd / "broll").glob("*.mp4"))) if (jd / "broll").is_dir() else 0,
                "edls": [e.name for e in edls],
                "mp4s": sorted(p.name for p in jd.glob("*.mp4") if p.name != "source.mp4"),
                "latest": latest,
            }

    (OUT_DIR / "workspace_audit.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[1/4] Workspace audit complete -> jobs/_ref15/workspace_audit.json (voices={ {k: len(v) for k, v in info['voices'].items()} })")
    return info


def ensure_15_refs(audit_info):
    existing_map = {}
    for rel in audit_info.get("existing_ref_files", []):
        p = ROOT / rel
        if p.suffix.lower() == ".mp4" and p.is_file():
            for rid in REF_IDS:
                if rid in p.name:
                    existing_map[rid] = p

    paths = {}
    for idx, rid in enumerate(REF_IDS, 1):
        dst = OUT_DIR / f"{rid}.mp4"
        if dst.is_file() and dst.stat().st_size > 50_000:
            paths[rid] = dst
            continue
        if rid in existing_map:
            paths[rid] = existing_map[rid]
            print(f"  [{idx:02d}/15] Reusing existing {rid}: {existing_map[rid].relative_to(ROOT)}")
            continue
        url = f"https://www.youtube.com/shorts/{rid}"
        print(f"  [{idx:02d}/15] Downloading {url} ...")
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "--no-playlist",
            "--write-info-json",
            "-f", "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]/b",
            "--merge-output-format", "mp4",
            "-o", str(OUT_DIR / f"{rid}.%(ext)s"),
            url,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if dst.is_file() and dst.stat().st_size > 50_000:
            paths[rid] = dst
        else:
            print(f"    ! Warning downloading {rid}: {r.stderr[-250:]}")
    print(f"[2/4] Reference videos ready: {len(paths)}/15")
    return paths


def _load_audio_22k(path, max_dur=None):
    cmd = ["ffmpeg", "-v", "error", "-i", str(path)]
    if max_dur:
        cmd += ["-t", str(max_dur)]
    cmd += ["-vn", "-ac", "1", "-ar", "22050", "-f", "f32le", "-"]
    b = subprocess.run(cmd, capture_output=True).stdout
    return np.frombuffer(b, np.float32)


def _logmel_flux(y):
    import librosa
    m = librosa.feature.melspectrogram(y=y, sr=22050, n_fft=1024, hop_length=256, n_mels=64, fmin=80, fmax=10000)
    L = librosa.power_to_db(m, ref=np.max, top_db=80).astype(np.float32)
    return np.maximum(np.diff(L, axis=1, prepend=L[:, :1]), 0.0)


def build_sfx_templates():
    import librosa
    from shorts import sfx_opus

    candidates = []
    seen = set()
    for cat, items in list(sfx_opus.FAMILY.items()) + list(sfx_opus.KIT_FAMILY.items()) + list(sfx_opus.LOCAL.items()):
        for s in items:
            fp = Path(s) if os.path.isfile(s) else (sfx_opus.KIT / s.split("/", 1)[0] / f"{s.split('/', 1)[1]}.wav" if "/" in s else Path(s))
            if fp.is_file() and str(fp) not in seen:
                seen.add(str(fp))
                candidates.append((cat, fp))

    lib_p = ROOT / "assets" / "sfx_library.json"
    clap_p = ROOT / "assets" / "sfx_clap.json"
    if lib_p.is_file():
        lib = json.loads(lib_p.read_text(encoding="utf-8"))
        clap = json.loads(clap_p.read_text(encoding="utf-8")) if clap_p.is_file() else {}
        for cat, items in lib.items():
            cnt = 0
            for it in items:
                fp = Path(it["file"])
                if not fp.is_file() or str(fp) in seen:
                    continue
                if clap.get(str(fp), {}).get("ok", True) is False:
                    continue
                seen.add(str(fp))
                candidates.append((cat, fp))
                cnt += 1
                if cnt >= 15:
                    break

    templates = []
    for cat, fp in candidates:
        try:
            y = _load_audio_22k(fp, max_dur=4.0)
            if len(y) < int(22050 * 0.08):
                continue
            _, idx = librosa.effects.trim(y, top_db=35)
            y = y[idx[0]:idx[0] + int(1.4 * 22050)]
            if len(y) < int(22050 * 0.08):
                continue
            T = _logmel_flux(y)
            T = T - T.mean()
            norm = np.linalg.norm(T)
            if norm > 1e-6:
                templates.append((cat, fp.name, str(fp), T / norm))
        except Exception:
            pass
    print(f"  Built {len(templates)} SFX templates")
    return templates


def scan_template(X, T, thr=0.48):
    n_mels, m = T.shape
    if X.shape[1] < m:
        return []
    num = sum(fftconvolve(X[b], T[b][::-1], mode="valid") for b in range(n_mels))
    c1 = np.concatenate([[0.0], np.cumsum(X.sum(0))])
    c2 = np.concatenate([[0.0], np.cumsum((X * X).sum(0))])
    s1, s2 = c1[m:] - c1[:-m], c2[m:] - c2[:-m]
    N = n_mels * m
    den = np.sqrt(np.maximum(s2 - s1 * s1 / N, N * 0.5))
    corr = num / den
    above = np.where(corr >= thr)[0]
    hits = []
    last = -1e9
    win = int(0.35 * 22050 / 256)
    for i in above:
        if i - last < win:
            continue
        j = i + int(np.argmax(corr[i:i + win]))
        hits.append((round(j * 256 / 22050, 2), round(float(corr[j]), 3)))
        last = j
    return hits


def analyze_visuals(vpath: Path):
    W, H, fps = 270, 480, 10
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(vpath), "-vf", f"fps={fps},scale={W}:{H}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True,
    ).stdout
    nf = len(raw) // (W * H * 3)
    if nf < 5:
        return {"cuts": [], "red_circles": []}
    frames = np.frombuffer(raw[:nf * W * H * 3], np.uint8).reshape(nf, H, W, 3)

    top_band = frames[:, 115:198, 15:255, :].astype(np.float32)
    bot_band = frames[:, 290:360, 15:255, :].astype(np.float32)
    band = np.concatenate([top_band, bot_band], axis=1)
    diffs = np.abs(band[1:] - band[:-1]).mean(axis=(1, 2, 3))
    cuts = []
    for i, df in enumerate(diffs):
        t = round((i + 1) / fps, 2)
        if df > 26.0 and (not cuts or t - cuts[-1] >= 0.4):
            cuts.append(t)

    panel = frames[:, 112:368, :, :]
    R, G, B = panel[:, :, :, 0].astype(np.int16), panel[:, :, :, 1].astype(np.int16), panel[:, :, :, 2].astype(np.int16)
    mask = (R > 210) & (G < 65) & (B < 65) & ((R - np.maximum(G, B)) > 150)
    mask[:, 95:168, 35:235] = False  # exclude center red text subtitles
    red_moments = []
    for i in range(nf):
        m = mask[i]
        cnt = int(m.sum())
        if cnt >= 45:
            ys, xs = np.where(m)
            bw, bh = int(xs.max() - xs.min()), int(ys.max() - ys.min())
            fill = cnt / max(1, bw * bh)
            if bw >= 18 and bh >= 18 and 0.03 <= fill <= 0.42:
                red_moments.append({
                    "t": round(i / fps, 2),
                    "box_1080p": [int(xs.min() * 4), int((ys.min() + 112) * 4), int(bw * 4), int(bh * 4)],
                })
    merged = []
    for rm in red_moments:
        if merged and rm["t"] - merged[-1]["t_end"] <= 0.35:
            merged[-1]["t_end"] = rm["t"]
            merged[-1]["frames"] += 1
        else:
            merged.append({"t_start": rm["t"], "t_end": rm["t"], "frames": 1, "box_1080p": rm["box_1080p"]})
    return {"cuts": cuts, "red_circles": [r for r in merged if r["frames"] >= 3]}


def make_contact_sheet(vpath: Path, out_jpg: Path, cols=4, rows=4):
    dur_str = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(vpath)],
        capture_output=True, text=True,
    ).stdout.strip()
    dur = max(1.0, float(dur_str or 50.0))
    n = cols * rows
    step = dur / (n + 0.5)
    tiles = []
    for k in range(n):
        t = round((k + 0.4) * step, 2)
        raw = subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(vpath), "-frames:v", "1", "-vf", "scale=270:480", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
            capture_output=True,
        ).stdout
        if len(raw) == 270 * 480 * 3:
            img = np.frombuffer(raw, np.uint8).reshape(480, 270, 3).copy()
            cv2.putText(img, f"{t:.1f}s", (10, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (0, 0, 0), 4, cv2.LINE_AA)
            cv2.putText(img, f"{t:.1f}s", (10, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (0, 255, 255), 2, cv2.LINE_AA)
            tiles.append(img)
    while len(tiles) < n:
        tiles.append(np.zeros((480, 270, 3), np.uint8))
    grid = np.vstack([np.hstack(tiles[r * cols:(r + 1) * cols]) for r in range(rows)])
    cv2.imwrite(str(out_jpg), grid, [int(cv2.IMWRITE_JPEG_QUALITY), 88])


def decompose_refs(ref_paths):
    from faster_whisper import WhisperModel
    wmodel = WhisperModel("base", device="cpu", compute_type="int8")

    has_librosa = False
    try:
        import librosa  # noqa: F401
        has_librosa = True
    except ImportError:
        pass
    templates = build_sfx_templates() if has_librosa else []

    videos = {}
    sfx_counter = Counter()

    for idx, (rid, vpath) in enumerate(ref_paths.items(), 1):
        info_p = OUT_DIR / f"{rid}.info.json"
        title, channel = "", ""
        if info_p.is_file():
            try:
                inf = json.loads(info_p.read_text(encoding="utf-8"))
                title = inf.get("title", "")
                channel = inf.get("channel") or inf.get("uploader") or ""
            except Exception:
                pass
        dur_str = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(vpath)],
            capture_output=True, text=True,
        ).stdout.strip()
        dur = round(float(dur_str or 0), 2)

        vis = analyze_visuals(vpath)
        cuts = vis["cuts"]
        bounds = [0.0] + cuts + [dur]
        shot_durs = [round(b - a, 2) for a, b in zip(bounds, bounds[1:]) if b - a > 0.05]

        pcm16 = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(vpath), "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
            capture_output=True,
        ).stdout
        arr16 = np.frombuffer(pcm16, np.int16).astype(np.float32) / 32768.0
        segs_raw, _ = wmodel.transcribe(arr16, vad_filter=True, condition_on_previous_text=False)
        segs = []
        for s in segs_raw:
            clip = arr16[int(s.start * 16000):int(s.end * 16000)]
            lang = "ko" if re.search(r"[가-힣]", s.text) else "en"
            if len(clip) >= 6400:
                try:
                    dl, prob, _ = wmodel.detect_language(clip)
                    if prob > 0.65 and dl in ("ko", "en"):
                        lang = dl
                except Exception:
                    pass
            txt = s.text.strip()
            if lang == "ko" and not re.search(r"[가-힣]", txt) and len(clip) >= 4800:
                ks, _ = wmodel.transcribe(clip, language="ko", condition_on_previous_text=False)
                txt = " ".join(x.text.strip() for x in ks).strip() or txt
            segs.append({"a": round(s.start, 2), "b": round(s.end, 2), "lang": lang, "text": txt})

        sfx_hits = []
        if templates:
            y22 = _load_audio_22k(vpath)
            X = _logmel_flux(y22)
            raw_hits = []
            for cat, fname, fpath, T in templates:
                for t_hit, corr in scan_template(X, T, thr=0.48):
                    raw_hits.append({"t": t_hit, "corr": corr, "cat": cat, "name": fname})
            raw_hits.sort(key=lambda h: -h["corr"])
            kept = []
            for h in raw_hits:
                if all(abs(h["t"] - k["t"]) >= 0.28 for k in kept):
                    near_cut = any(abs(h["t"] - c) <= 0.18 for c in [0.0] + cuts)
                    active_seg = next((sg for sg in segs if sg["a"] - 0.2 <= h["t"] <= sg["b"] + 0.2), None)
                    h["near_cut"] = near_cut
                    h["context"] = f"[{active_seg['lang']}] {active_seg['text'][:36]}" if active_seg else ""
                    kept.append(h)
                    sfx_counter[f"{h['cat']}:{h['name']}"] += 1
            sfx_hits = sorted(kept, key=lambda h: h["t"])

        videos[rid] = {
            "title": title,
            "channel": channel,
            "duration_sec": dur,
            "shot_count": len(shot_durs),
            "median_shot_sec": round(float(np.median(shot_durs)), 2) if shot_durs else 0,
            "min_shot_sec": round(float(min(shot_durs)), 2) if shot_durs else 0,
            "cuts": cuts,
            "red_circles": vis["red_circles"],
            "ko_sec": round(sum(s["b"] - s["a"] for s in segs if s["lang"] == "ko"), 1),
            "en_sec": round(sum(s["b"] - s["a"] for s in segs if s["lang"] == "en"), 1),
            "segments": segs,
            "sfx_hits": sfx_hits,
        }
        print(
            f"  [{idx:02d}/15] {rid} ({dur:.1f}s | {channel[:12]}) '{title[:28]}' -> "
            f"shots={len(shot_durs)} (med {videos[rid]['median_shot_sec']}s), "
            f"red_circles={len(vis['red_circles'])}, sfx_hits={len(sfx_hits)}"
        )

    sheet_ids = ["YVBql8gjaUg", "QMJtjJz4M6w", "2jJoIbdciDY", "h00vdwsFphw", "vbxJ_v132ao"]
    for rid, rdata in videos.items():
        if rdata["red_circles"] and rid not in sheet_ids and len(sheet_ids) < 8:
            sheet_ids.append(rid)
    for rid in sheet_ids:
        if rid in ref_paths:
            make_contact_sheet(ref_paths[rid], OUT_DIR / f"sheet_{rid}.jpg")

    summary = {
        "ref_count": len(videos),
        "median_duration_sec": round(float(np.median([r["duration_sec"] for r in videos.values()])), 2) if videos else 0,
        "median_shot_count": round(float(np.median([r["shot_count"] for r in videos.values()])), 1) if videos else 0,
        "median_shot_duration_sec": round(float(np.median([r["median_shot_sec"] for r in videos.values()])), 2) if videos else 0,
        "total_red_circles_across_15": sum(len(r["red_circles"]) for r in videos.values()),
        "top_matched_sfx_across_15": sfx_counter.most_common(35),
        "videos": videos,
    }
    (OUT_DIR / "ref15_report.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[4/4] Saved full 15-reference decomposition -> jobs/_ref15/ref15_report.json")


if __name__ == "__main__":
    audit = audit_workspace()
    refs = ensure_15_refs(audit)
    print("[3/4] Decomposing all 15 reference Shorts...")
    decompose_refs(refs)
