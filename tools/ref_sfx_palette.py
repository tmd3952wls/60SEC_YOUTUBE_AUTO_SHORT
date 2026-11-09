"""참고 쇼츠 효과음 팔레트 찾기 (earshot CLAP 임베딩).

ext/earshot/.venv 파이썬으로 실행:
  python tools/ref_sfx_palette.py <timeline_json_dir> <stems_dir> <out.json> <라이브러리 폴더...>

1) earshot timeline 결과(참고 영상의 음악+효과음 스템)에서 배경보다 확 튀는 소리(효과음일 가능성 높음)를 뽑고
2) 라이브러리 소리마다 앞부분 1.2초를 같은 방식으로 임베딩해
3) 참고 효과음마다 가장 가까운 라이브러리 소리를 찾음 → 자주, 가깝게 뽑히는 소리 = 참고 영상과 닮은 팔레트.
"""
import glob
import json
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ext", "earshot"))
from earshot import audio  # noqa: E402
from earshot.vocab import embed_spans  # noqa: E402

tl_dir, stems_dir, out_path, libs = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]


def norm(m):
    return m / (np.linalg.norm(m, axis=-1, keepdims=True) + 1e-12)


# ---- 참고 효과음 후보
refs = []
for f in sorted(glob.glob(os.path.join(tl_dir, "*.json"))):
    vid = os.path.splitext(os.path.basename(f))[0]
    tl = json.load(open(f, encoding="utf-8"))
    stem = os.path.join(stems_dir, vid, "no_vocals.wav")
    dur = tl["duration"]
    for ev in tl["events"]:
        if ev.get("prominence_db", 0) < float(os.environ.get("MINPROM", 12)) or ev.get("peak_dbfs", -99) < -24 or ev.get("starts_file"):
            continue
        L = min(1.2, max(0.25, ev.get("length_ms", 300) / 1000))
        s, e = max(0.0, ev["t"] - 0.01), min(dur, ev["t"] + L)
        refs.append({"vid": vid, "t": round(ev["t"], 2), "s": s, "e": e, "prom": ev["prominence_db"],
                     "kind": ev.get("kind", "-"), "label": ev.get("label", ""), "path": stem})
print(f"참고 효과음 후보 {len(refs)}개")
R = norm(embed_spans([(r["path"], r["s"], r["e"]) for r in refs], pad="zero"))

# ---- 라이브러리
lib = []
for d in libs:
    for p in glob.glob(os.path.join(d, "**", "*.*"), recursive=True):
        if os.path.splitext(p)[1].lower() not in (".wav", ".mp3", ".ogg", ".flac", ".m4a"):
            continue
        try:
            du = audio.duration(p)
        except Exception:
            continue
        if du > 4.5 or du < 0.05:  # 배경음악·긴 녹음 제외
            continue
        lib.append({"path": p, "dur": du, "lib": os.path.basename(d.rstrip("/\\"))})
print(f"라이브러리 소리 {len(lib)}개")
LIB = norm(embed_spans([(x["path"], 0.0, min(1.2, x["dur"])) for x in lib], pad="zero"))

S = R @ LIB.T  # (ref, lib) 코사인
hits = defaultdict(lambda: {"n": 0, "score": 0.0, "examples": []})
per_ref = []
for i, r in enumerate(refs):
    top = np.argsort(-S[i])[:3]
    per_ref.append({**{k: r[k] for k in ("vid", "t", "prom", "kind", "label")},
                    "top": [(lib[j]["path"], round(float(S[i, j]), 3)) for j in top]})
    j = top[0]
    h = hits[lib[j]["path"]]
    h["n"] += 1
    h["score"] += float(S[i, j])
    if len(h["examples"]) < 4:
        h["examples"].append(f'{r["vid"]}@{r["t"]}')
pal = sorted(({"path": p, **v, "mean_cos": round(v["score"] / v["n"], 3)} for p, v in hits.items()),
             key=lambda x: (-x["n"], -x["mean_cos"]))
by_lib = defaultdict(list)
for i in range(len(refs)):
    best = defaultdict(float)
    for j in range(len(lib)):
        best[lib[j]["lib"]] = max(best[lib[j]["lib"]], float(S[i, j]))
    for k, v in best.items():
        by_lib[k].append(v)
summary = {k: {"median_best_cos": round(float(np.median(v)), 3)} for k, v in by_lib.items()}
json.dump({"n_refs": len(refs), "n_lib": len(lib), "lib_summary": summary, "palette": pal[:80], "per_ref": per_ref},
          open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("라이브러리별 '가장 가까운 소리' 유사도 중앙값:", summary)
for x in pal[:30]:
    print(f'{x["n"]:3d}회  cos {x["mean_cos"]:.3f}  {os.path.basename(x["path"])}  ({", ".join(x["examples"][:2])})')
