import sys, json, copy, shutil, subprocess
sys.path.insert(0, r"C:\Users\tmd39\Desktop\YOUTUBE_AUTO")
sys.stdout.reconfigure(encoding="utf-8")
from shorts.common import JOBS, load_config, read_json
from shorts.edl import render_edl
cfg = load_config()
pre = read_json(r"C:\Users\tmd39\Desktop\YOUTUBE_AUTO\editor\presets\해외쇼쇼.json").get("config", {})
def merge(b, o):
    for k, v in o.items():
        if isinstance(v, dict) and isinstance(b.get(k), dict): merge(b[k], v)
        else: b[k] = v
merge(cfg, pre)
cfg["render"]["no_sfx"] = True
job = JOBS / "vulcan_rattrap"
out, total, log = render_edl(job, job / "v5_edl.json", cfg, out_name="v6_nosfx.mp4")
(job / "v6_nosfx_log.txt").write_text("\n".join(log), encoding="utf-8")
d = job / "sound_v6"; d.mkdir(exist_ok=True)
subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(job / "edl_tmp" / "body.mp4"), "-vn", "-ac", "2", "-ar", "48000", "-c:a", "pcm_s24le", str(d / "vo.wav")], check=True)
shutil.copy2(job / "edl_tmp" / "export.json", d / "export_nosfx.json")
print("done", total)
