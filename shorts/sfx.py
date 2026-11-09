"""기본 효과음 생성. assets/sfx 에 같은 이름(whoosh.wav 등)의 파일을 넣으면 그걸 우선 사용."""
from .common import ASSETS, ffmpeg

RECIPES = {
    "whoosh": "anoisesrc=d=0.5:c=pink:a=0.7,highpass=f=400,lowpass=f=5000,"
              "afade=t=in:d=0.3:curve=exp,afade=t=out:st=0.3:d=0.2",
    "pop": "aevalsrc='0.8*sin(2*PI*(400+3500*t)*t)*exp(-28*t)':d=0.15",
    "ding": "aevalsrc='0.5*(sin(2*PI*1568*t)+0.6*sin(2*PI*2349*t))*exp(-4*t)':d=1.0",
    "boom": "aevalsrc='0.9*sin(2*PI*(90-50*t)*t)*exp(-2.5*t)':d=1.2,lowpass=f=300,volume=2",
}


def ensure_sfx():
    d = ASSETS / "sfx"
    d.mkdir(parents=True, exist_ok=True)
    for name, recipe in RECIPES.items():
        if not any((d / f"{name}{ext}").exists() for ext in (".wav", ".mp3")):
            ffmpeg("-f", "lavfi", "-i", recipe, "-ar", "48000", "-ac", "2", d / f"{name}.wav")


def sfx_path(name):
    for ext in (".wav", ".mp3"):
        p = ASSETS / "sfx" / f"{name}{ext}"
        if p.exists():
            return p
    return None
