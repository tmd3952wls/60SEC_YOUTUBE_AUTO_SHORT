import sys, time
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
from pathlib import Path
sys.path.insert(0, r"C:\Users\tmd39\Desktop\YOUTUBE_AUTO")
from shorts import source, scenes
from shorts.common import write_json, duration
job = Path(r"C:\Users\tmd39\Desktop\YOUTUBE_AUTO\jobs\goldberg")
t=time.time()
if not (job/"source.mp4").exists():
    source.fetch("https://www.youtube.com/watch?v=Efpe1MnKHVk", job); print("fetched", duration(job/"source.mp4"), time.time()-t)
tr = source.transcribe(job/"source.mp4", job, "small"); print("transcribed", len(tr), time.time()-t)
cuts = scenes.detect_cuts(job/"source.mp4"); write_json(job/"cuts.json", cuts); print("cuts", len(cuts), time.time()-t)
