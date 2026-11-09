"""편집기에서 부르는 렌더 작업 (한 번에 하나).

python editor/render_worker.py --job 이름 --edl v5_edl.json --out edit_v6.mp4 [--items 0,1,2] [--preset 해외쇼쇼]
결과: jobs/이름/<out>.mp4, <out>_log.txt, <out>_meta.json(어떤 EDL·박자로 만들었는지)
"""
import argparse
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

from shorts.common import JOBS, load_config  # noqa: E402
from shorts.edl import render_edl  # noqa: E402

PRESETS = Path(__file__).resolve().parent / "presets"


def deep_merge(base, over):
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", required=True)
    ap.add_argument("--edl", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--items", default="")
    ap.add_argument("--preset", default="")
    a = ap.parse_args()

    job = JOBS / a.job
    edl_path = job / a.edl
    items = [int(i) for i in a.items.split(",") if i.strip()]
    if items:  # 일부 박자만 미리보기
        e = json.loads(edl_path.read_text(encoding="utf-8"))
        e["items"] = [e["items"][i] for i in items]
        edl_path = job / "edl_tmp" / ("preview_" + a.out.replace(".mp4", "") + "_edl.json")
        edl_path.parent.mkdir(exist_ok=True)
        edl_path.write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")

    cfg = copy.deepcopy(load_config())
    preset = {}
    if a.preset:
        preset = json.loads((PRESETS / f"{a.preset}.json").read_text(encoding="utf-8"))
        deep_merge(cfg, preset.get("config", {}))

    print(f"렌더 시작: {a.job}/{a.edl} → {a.out}" + (f" (박자 {a.items})" if items else ""))
    out, total, log = render_edl(job, edl_path, cfg, out_name=a.out)
    stem = a.out.replace(".mp4", "")
    (job / f"{stem}_log.txt").write_text("\n".join(log), encoding="utf-8")
    (job / f"{stem}_meta.json").write_text(json.dumps(
        {"edl": a.edl, "items": items or None, "preset": a.preset, "duration": round(total, 2),
         "draft": a.edl.startswith("edl_tmp")},
        ensure_ascii=False, indent=1), encoding="utf-8")
    warn = [l for l in log if "⚠" in l]
    print(f"완료: {total:.2f}초" + (" / 경고: " + "; ".join(warn) if warn else ""))


if __name__ == "__main__":
    main()
