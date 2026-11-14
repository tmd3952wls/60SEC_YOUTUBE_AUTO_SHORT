"""3단계: 내레이션 TTS.

provider
- capcut   : CapCut '활기찬 바리톤' (1.1배속) 전용 (assets/voices/<voice>/<md5>.wav 수확본 최우선 + 공식 ELEVENLABS_API_KEY 연동 지원; 타 음성 대체 금지)
- fish     : Fish Audio API  (FISH_API_KEY, config tts.fish.reference_id)
- typecast : Typecast API    (TYPECAST_API_KEY, config tts.typecast.voice_id)
- sapi     : Windows 기본 한국어 음성(Heami). 무료 테스트용, 품질 낮음.
결과는 앞뒤 무음을 잘라낸 48kHz 스테레오 wav. 같은 문장은 캐시 재사용.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from .common import ffmpeg

# CapCut '활기찬 바리톤' 실제 내부 보이스 메타데이터 (draft_content.json 기준: tone_platform=11labs)
CAPCUT_ELEVENLABS_VOICES = {
    "vibrant_baritone": "rKZCRTvCRsUjB3zmsrOY",
}


def _post_audio(url, headers, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"TTS API 오류 {e.code}: {e.read()[:500].decode('utf-8', 'replace')}")


def _fish(text, out, c):
    audio = _post_audio("https://api.fish.audio/v1/tts",
                        {"Authorization": f"Bearer {os.environ['FISH_API_KEY']}",
                         "Content-Type": "application/json", "model": c["model"]},
                        {"text": text, "reference_id": c["reference_id"] or None,
                         "format": "wav", "prosody": {"speed": c["speed"]}, "latency": "normal"})
    out.write_bytes(audio)


def typecast_voices(model, gender=None):
    """Typecast 보이스 목록 (GET /v3/voices)."""
    q = f"model={model}" + (f"&gender={gender}" if gender else "")
    req = urllib.request.Request(f"https://api.typecast.ai/v3/voices?{q}",
                                 headers={"X-API-KEY": os.environ["TYPECAST_API_KEY"]})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Typecast 오류 {e.code}: {e.read()[:500].decode('utf-8', 'replace')}")


def _typecast(text, out, c):
    if not c.get("voice_id"):
        raise RuntimeError("config.json 의 tts.typecast.voice_id 가 비어 있습니다 "
                           "(python make_short.py voices 로 찾기)")
    body = {"text": text, "model": c["model"], "voice_id": c["voice_id"], "language": "kor",
            "output": {"audio_format": "wav", "audio_tempo": c["speed"], "audio_pitch": c.get("pitch", 0)}}
    if c.get("emotion_preset"):
        body["prompt"] = {"emotion_type": "preset", "emotion_preset": c["emotion_preset"],
                          "emotion_intensity": c.get("emotion_intensity", 1.0)}
    elif c.get("smart_emotion", True):
        body["prompt"] = {"emotion_type": "smart"}
    audio = _post_audio("https://api.typecast.ai/v1/text-to-speech",
                        {"X-API-KEY": os.environ["TYPECAST_API_KEY"], "Content-Type": "application/json"},
                        body)
    out.write_bytes(audio)


def _sapi(text, out, c):
    t = text.replace("'", "''")
    ps = ("Add-Type -AssemblyName System.Speech; "
          "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
          f"$s.SelectVoice('{c['voice']}'); $s.Rate={c['rate']}; "
          f"$s.SetOutputToWaveFile('{out}'); $s.Speak('{t}'); $s.Dispose()")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True, capture_output=True)


def _elevenlabs_capcut_voice(text: str, dst_wav: Path, voice_id: str, speed: float, api_key: str) -> None:
    """공식 ElevenLabs REST API 로 CapCut 동일 보이스(rKZCRTvCRsUjB3zmsrOY) 생성 후 1.1배속 48kHz 스테레오 저장."""
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128"
    headers = {
        "xi-api-key": api_key.strip(),
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    body = {
        "text": text.strip(),
        "model_id": "eleven_multilingual_v2",
    }
    mp3_bytes = _post_audio(url, headers, body)
    tmp_mp3 = dst_wav.with_suffix(".11labs.mp3")
    dst_wav.parent.mkdir(parents=True, exist_ok=True)
    try:
        tmp_mp3.write_bytes(mp3_bytes)
        af = ["-af", f"atempo={speed}"] if abs(speed - 1.0) > 1e-3 else []
        ffmpeg("-i", tmp_mp3, *af, "-ar", "48000", "-ac", "2", dst_wav)
    finally:
        tmp_mp3.unlink(missing_ok=True)


def _capcut(text, out: Path, c):
    """CapCut AI 목소리 ('활기찬 바리톤' vibrant_baritone 1.1배속 전용 — 타 음성 대체 엄격 금지):
    1) assets/voices/<voice>/<md5(문장)>.wav 수확본이 있으면 즉시 사용
    2) ELEVENLABS_API_KEY 가 설정된 경우 CapCut 동일 성우 ID(rKZCRTvCRsUjB3zmsrOY) 공식 API 로 생성·캐시 후 사용
    3) 둘 다 없으면 다른 목소리(여성 SAPI·타 TTS)로 절대 대체하지 않고 명시적 오류를 발생시킴
    """
    from .common import ASSETS
    voice = c.get("voice", "vibrant_baritone")
    speed = float(c.get("speed", 1.1))
    f = ASSETS / "voices" / voice / (hashlib.md5(text.strip().encode("utf-8")).hexdigest()[:16] + ".wav")
    if f.exists():
        shutil.copy2(f, out)
        return
    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    voice_id = c.get("elevenlabs_voice_id") or CAPCUT_ELEVENLABS_VOICES.get(voice, "")
    if api_key and voice_id:
        _elevenlabs_capcut_voice(text, f, voice_id, speed, api_key)
        shutil.copy2(f, out)
        return
    raise RuntimeError(
        f"CapCut '{voice}' ({speed}x) 전용 음성 파일이 없습니다 (타 음성 대체 금지): {text}\n"
        f"  → CapCut Desktop 'voice_<작업>_{voice}' 프로젝트에서 '활기찬 바리톤' 텍스트 읽기 후 "
        f"`python tools/capcut_voice.py harvest --job <작업> --voice {voice} --fallback-speed {speed}` 를 실행하거나, "
        f".env 에 ELEVENLABS_API_KEY 를 설정하세요."
    )


PROVIDERS = {
    "fish": _fish,
    "typecast": _typecast,
    "sapi": _sapi,
    "capcut": _capcut,
}


def synth(text, tts_dir: Path, cfg):
    tcfg = cfg["tts"]
    prov = tcfg["provider"]
    pcfg = tcfg.get(prov, {})
    key = hashlib.md5(json.dumps([prov, pcfg, text], ensure_ascii=False).encode()).hexdigest()[:12]
    pause = tcfg.get("max_pause", 0.08)
    thr = int(tcfg.get("pause_threshold_db", -35))  # 2026-11-09: -35 로는 숨소리 섞인 0.3초 쉼이 안 줄어 '지루' → -30
    final = tts_dir / f"{key}_p{int(pause * 1000)}t{-thr}n.wav"  # n: 무음 판정 전에 음량을 맞춘 판 (2026-11-08)
    if final.exists():
        return final
    tts_dir.mkdir(parents=True, exist_ok=True)
    raw = tts_dir / f"{key}.raw.wav"  # API 원본은 보관 → 후처리만 바꿀 땐 다시 과금되지 않음
    if not raw.exists():
        PROVIDERS[prov](text, raw, pcfg)
    # 앞뒤 무음 제거 + 문장 사이 쉼을 max_pause 이하로 압축(말이 비지 않게) + 포맷 통일
    trim = "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.03"
    squeeze = (f"silenceremove=stop_periods=-1:stop_duration={pause}:stop_threshold={thr}dB:"
               f"stop_silence={pause}")
    vd = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(raw), "-af", "volumedetect", "-f", "null", "-"],
                        capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    m = re.search(r"max_volume: (-?[\d.]+) dB", vd)
    gain = -1.0 - float(m.group(1)) if m else 0.0
    af = f"volume={gain:.2f}dB,{trim},areverse,{trim},areverse,{squeeze}"
    extra = float(tcfg.get("extra_tempo", 1.0))
    if abs(extra - 1.0) > 0.01:
        af += f",atempo={extra}"
    ffmpeg("-i", raw, "-af", af, "-ar", "48000", "-ac", "2", final)
    return final
