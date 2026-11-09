"""효과음 파일마다 사람 목소리가 섞여 있는지 Demucs 로 판정 → assets/sfx_voice.json {파일: 목소리비율}
.venv-whisperx 파이썬으로 실행: python sfx_voice_check.py <목록.json> <출력.json>
"""
import json
import sys

import numpy as np
import torch
from demucs.apply import apply_model
from demucs.audio import AudioFile
from demucs.pretrained import get_model


def main():
    files = json.load(open(sys.argv[1], encoding="utf-8"))
    model = get_model("htdemucs")
    model.eval()
    vi = model.sources.index("vocals")
    out = {}
    for f in files:
        try:
            wav = AudioFile(f).read(streams=0, samplerate=model.samplerate, channels=model.audio_channels)
            if wav.shape[-1] < model.samplerate // 2:  # 너무 짧으면 0.5초로 패딩
                wav = torch.nn.functional.pad(wav, (0, model.samplerate // 2 - wav.shape[-1]))
            with torch.no_grad():
                src = apply_model(model, wav[None], device="cpu", progress=False)[0]
            e = (src ** 2).mean(dim=(1, 2)).numpy()
            out[f] = round(float(e[vi] / (e.sum() + 1e-12)), 3)
        except Exception as ex:
            out[f] = None
        print(f"{out[f]}\t{f}", flush=True)
    json.dump(out, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=0)


if __name__ == "__main__":
    main()
