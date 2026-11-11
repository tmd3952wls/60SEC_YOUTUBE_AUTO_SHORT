"""BGM 깔기 (2026-11-10, 참고 쇼츠 4q8E4EPcgew 측정 기준).

참고 쇼츠(해외쇼쇼, BGM = Ogryzek "AURA (Ultra Slowed + Reverb)")를 Demucs 로 목소리/음악 분리 후
원곡과 맞춰 본 결과:
- 곡 처음(0.4초 지점)부터 그대로 깔림, 속도 변화 없음
- 말하는 동안 BGM 은 목소리보다 약 9dB 작음 (순간 음량 중앙값 기준)
- 말이 멈춘 틈에는 약 6.6dB 올라옴 (덕킹)

EDL 최상위에 "bgm": {"file": "assets/bgm/xxx.wav", "start": 0.4} 를 넣으면 깔린다.
선택: "under_voice_db"(기본 -9), "duck_db"(기본 6.6), "fade_out"(기본 1.0초).
"""
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

from .common import ffmpeg
from .sfx_level import SR, _integrated, _momentary

ROOT = Path(__file__).resolve().parent.parent


def _load(path, start=0.0, dur=None):
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}"]
    if dur:
        cmd += ["-t", f"{dur:.3f}"]
    cmd += ["-i", str(path), "-vn", "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"]
    y = np.frombuffer(subprocess.run(cmd, capture_output=True, check=True).stdout, np.float32)
    return y.reshape(-1, 2).astype(np.float64)


def _smooth_activity(t, m, thr, n, attack=0.08, release=0.35):
    """말하는 구간 0~1 곡선 (샘플 단위). 올라갈 땐 빠르게, 내려갈 땐 천천히."""
    act = (m > thr).astype(float)
    # 짧은 틈(0.25초 미만)은 말하는 중으로 봄 → BGM 이 단어 사이마다 출렁이지 않게
    k = int(0.25 / (t[1] - t[0]))
    for i in range(len(act)):
        if act[i] == 0 and act[max(0, i - k):i].any() and act[i + 1:i + 1 + k].any():
            act[i] = 1.0
    out = np.zeros_like(act)
    dt = t[1] - t[0]
    a_up, a_dn = 1 - np.exp(-dt / attack), 1 - np.exp(-dt / release)
    v = act[0]
    for i, x in enumerate(act):
        v += (x - v) * (a_up if x > v else a_dn)
        out[i] = v
    return np.interp(np.arange(n) / SR, t, out)


def apply(body, video, out, total, bcfg, work, master_db, master_lufs=-14.0):
    """video(효과음까지 믹스된 완성본)에 BGM 을 덕킹해서 깔고 out 으로 저장.
    반환: (CapCut 용 정보 dict, 로그 줄 목록). CapCut 용 BGM 파일은 덕킹·크기를 미리 입힌 wav(마스터 전 크기)."""
    work.mkdir(parents=True, exist_ok=True)
    f = Path(bcfg["file"])
    f = f if f.is_absolute() else ROOT / f
    n = int(round(total * SR))
    voice = _load(body)[:n]
    voice = np.pad(voice, ((0, n - len(voice)), (0, 0)))
    music = _load(f, bcfg.get("start", 0.4))
    if len(music) < n:  # 곡이 영상보다 짧으면 이어 붙임
        music = np.tile(music, (n // len(music) + 1, 1))
    music = music[:n]

    tv, mv = _momentary(voice)
    tm, mm = _momentary(music)
    Iv = _integrated(voice)
    speak = mv > Iv - 8
    under, duck = bcfg.get("under_voice_db", -9.0), bcfg.get("duck_db", 6.6)
    # 말하는 동안 BGM 순간 음량 중앙값 = 목소리 중앙값 + under
    g0 = (np.median(mv[speak]) + under) - np.median(mm[:len(mv)][speak[:len(mm)]])
    act = _smooth_activity(tv, mv, Iv - 8, n)
    gain_db = g0 + duck * (1 - act)
    fo = bcfg.get("fade_out", 1.0)
    env = 10 ** (gain_db / 20)
    tail = np.arange(n) / SR > total - fo
    env[tail] *= np.clip((total - np.arange(n)[tail] / SR) / fo, 0, 1)
    bgm = music * env[:, None]
    bgm_file = work / f"bgm_{f.stem}.wav"
    sf.write(bgm_file, bgm.astype(np.float32), SR, subtype="FLOAT")

    # 완성본(이미 마스터 크기)에 같은 마스터 게인으로 섞고 다시 -14 LUFS 로
    full = _load(video)[:n]
    full = np.pad(full, ((0, n - len(full)), (0, 0)))
    mix = full + bgm * 10 ** (master_db / 20)  # 목소리(body) → 완성본에 붙은 것과 같은 마스터 게인
    fix = master_lufs - _integrated(mix)
    mix_file = work / "mix_bgm.wav"
    sf.write(mix_file, (mix * 10 ** (fix / 20)).astype(np.float32), SR, subtype="FLOAT")
    ffmpeg("-i", video, "-i", mix_file, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
           "-af", "alimiter=limit=0.89:attack=3:release=60:level=0", "-c:a", "aac", "-b:a", "192k",
           "-movflags", "+faststart", "-t", f"{total:.3f}", out)

    tb, mb = _momentary(bgm)
    k = min(len(mb), len(mv))
    gap = ~speak[:k] & (mv[:k] > -70)
    log = [f"BGM: {f.name} ({bcfg.get('start', 0.4):.1f}초부터), 기본 {g0:+.1f}dB, 말 틈 +{duck:.1f}dB 덕킹, "
           f"끝 {fo:.1f}초 페이드아웃",
           f"  말하는 동안 BGM-목소리 {np.median(mb[:k][speak[:k]] - mv[:k][speak[:k]]):+.1f}dB (참고 -9.2dB)"
           + (f", 말 틈 BGM 이 말할 때보다 {np.median(mb[:k][gap]) - np.median(mb[:k][speak[:k]]):+.1f}dB" if gap.sum() > 20 else ""),
           f"  최종 음량 보정 {fix:+.2f}dB → {master_lufs} LUFS"]
    return {"file": str(bgm_file), "name": f.name, "master_fix_db": float(fix)}, log
