"""EDL(편집 결정 목록) 렌더러 — 참고 영상 편집 문법을 그대로 재현하기 위한 저수준 렌더러.

자동 대본(plan.json) 렌더러와 달리, 한 항목(item)의 '소리'와 '그림'을 따로 지정한다.
  item = 소리 한 덩어리 (TTS 내레이션 또는 원본 대사 단어 구간)
  shots = 그 소리 위에 깔리는 그림들. 각 샷은 '몇 번째 단어에서 컷' 할지로 시작 시점을 지정 (L컷)
  circle = 원본 픽셀 좌표의 대상 박스 + 강조 시작 단어 → 최종 크롭·확대를 반영해 프레임마다 위치/크기 계산
  flash  = 항목 시작 순간 색 번쩍임 (참고 영상의 분홍/초록 전환)
  subs   = 자막 덩어리. 내레이션은 어절 수로, 원본 대사는 단어 번호로 시작 시점 지정
"""
import json
import re
from pathlib import Path

from .align import align_all
from .common import ASSETS, duration, ffmpeg, filter_path, read_json, run, write_json
from .render import ass_time, lufs_of, plain, voice_gain
from .sfxlib import pick as pick_sfx
from .subfx import _ellipse, bgr, merge_short, money_green, money_icon_events, neon_events, parse_spans, ref_sub_events
from .tts import synth

import subprocess

import numpy as np


def _env_db(path, hop=160):
    """10ms RMS 음량(dB) 곡선 (16kHz 모노)."""
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                         capture_output=True).stdout
    x = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768
    n = len(x) // hop
    return 20 * np.log10(np.sqrt((x[:n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-6)

PW, PH = 1080, 1050  # 영상 패널

# 자막에만 쓰는 재미 표현 (참고: 셀 인사이트 쇼츠 "ㄹㅇ 간단한 아이디어죠", "괜찮아용;;", "보시죠 ㅎ")
# TTS 에는 읽을 말로 바꾸거나 빼고, 자막 어절 수 셀 때도 같은 규칙으로 → 자막·목소리 싱크 유지
SAY = {"ㄹㅇ": "진짜"}


def tts_say(text):
    out = []
    for w in text.split():
        w = SAY.get(w, w)
        w = re.sub(r"[ㄱ-ㅎㅏ-ㅣ;@~]+", "", w)  # ㅎㅎ ㅋㅋ ㅠㅠ ;; @ 같은 건 소리 내지 않음
        if w.strip():
            out.append(w)
    return " ".join(out)


def _snap_onsets(wav, wl, log, tag):
    """단어 시작을 '실제로 목소리가 다시 나는 순간'에 붙임 (2026-11-09).
    정렬기는 앞 단어 뒤 쉼(0.1~0.3초)을 다음 단어에 붙여 시작을 일찍 잡곤 함 → 자막이 말보다 먼저 뜸.
    0.09초 이상 조용한 구간이 단어 시작 근처(앞 0.25초 ~ 뒤 0.15초)에서 끝나면 그 끝을 단어 시작으로."""
    e = _env_db(wav)  # 10ms 간격
    if not len(e) or not wl:
        return wl
    thr = np.percentile(e, 95) - 28
    quiet = e < thr
    runs, i = [], 0  # (조용 시작, 조용 끝) 초
    while i < len(quiet):
        if quiet[i]:
            j = i
            while j < len(quiet) and quiet[j]:
                j += 1
            if j - i >= 9 and j < len(quiet):
                runs.append((i / 100, j / 100))
            i = j
        else:
            i += 1
    out = []
    for k, w in enumerate(wl):
        ws = w[1]
        lo = out[-1][1] + 0.05 if out else -1.0  # 앞 단어 시작보다 뒤로만 (두 단어가 같은 쉼 끝에 붙지 않게)
        cand = [b for a, b in runs if a <= ws + 0.15 and ws - 0.25 <= b <= ws + 0.45 and b < w[2] and b > lo]
        if cand:
            nb = min(cand, key=lambda b: abs(b - ws))
            if abs(nb - ws) >= 0.03:
                d = nb - ws
                log.append(f"  ⤳ {tag} '{w[0]}' 시작 {ws:.2f} → {nb:.2f}s (실제 목소리 시작에 맞춤 {d * 1000:+.0f}ms)")
                w = (w[0], nb, w[2]) + ((w[3] + d,) if len(w) > 3 else ())
        out.append(w)
    return out



def _item_audio(job, it, cfg, words_src, tmp, idx):
    """항목 소리 파일 + 출력 기준 단어 시간 [(word, s, e)]."""
    R = cfg["render"]
    if it["type"] == "narration":
        say = tts_say(plain(it["text"]))
        wav = synth(say, job / "tts", cfg)
        al = align_all([(str(wav), say)], cfg)[str(wav)] or []
        wl = [(w["word"], w["start"], w["end"]) for w in al]
        return wav, duration(wav), wl, voice_gain(lufs_of(wav), R)
    # 원본 대사: 지정한 줄(ids)의 단어들, 단어 사이 긴 침묵은 '소리에서만' 잘라냄 (그림은 샷이 따로 채움)
    ws = [w for i in it["ids"] for w in words_src[str(i)]]
    if "word_range" in it:
        a, b = it["word_range"]
        ws = ws[a:b]
    if it.get("skip_words"):  # 중간에 끼어든 다른 사람의 감탄사(Whoa 등)를 소리에서 뺌. 인덱스는 word_range 적용 뒤 기준
        sk = set(it["skip_words"])
        ws = [w for k, w in enumerate(ws) if k not in sk]
    pieces = []
    for w in ws:
        if pieces and w["s"] - pieces[-1][1] <= it.get("max_gap", 0.3):
            pieces[-1][1] = w["e"]
        else:
            pieces.append([w["s"], w["e"]])
    pieces = [[p[0] - 0.04, p[1] + 0.06] for p in pieces]
    if it.get("audio_end"):  # 마지막 말 뒤로 원본을 그대로 더 이어감(화면·소리 모두 원본 실시간)
        pieces[-1][1] = max(pieces[-1][1], it["audio_end"])
    if it.get("audio_cut"):  # 정렬기가 마지막 단어 끝을 실제 목소리보다 길게 잡은 경우, 실제 목소리 끝에서 자름
        pieces[-1][1] = min(pieces[-1][1], it["audio_cut"])
    out = tmp / f"a{idx:02d}.wav"
    # 원본 방송 음악·현장음 제거: Demucs 로 분리한 대사만(source_vocals.wav) 사용 → 대사/내레이션 사이 음악이 켜졌다 꺼지지 않음
    asrc = job / "source_vocals.wav"
    if not (R.get("clip_vocals_only", True) and asrc.exists()):
        asrc = job / "source.mp4"
    inputs, fc = [], []
    for k, (a, b) in enumerate(pieces):
        inputs += ["-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", str(asrc)]
        fc.append(f"[{k}:a]aresample=48000,aformat=channel_layouts=stereo,afade=t=in:d=0.01,"
                  f"afade=t=out:st={b - a - 0.015:.3f}:d=0.015[p{k}]")
    fc.append("".join(f"[p{k}]" for k in range(len(pieces))) + f"concat=n={len(pieces)}:v=0:a=1[a]")
    ffmpeg(*inputs, "-filter_complex", ";".join(fc), "-map", "[a]", out)
    # 단어의 출력 시간
    wl, off = [], 0.0
    for a, b in pieces:
        for w in ws:
            if a <= w["s"] < b:
                wl.append((w["w"], off + w["s"] - a, off + w["e"] - a, w["s"]))
        off += b - a
    src_l = lufs_of(asrc, pieces[0][0], pieces[-1][1] - pieces[0][0])
    return out, off, wl, voice_gain(src_l, R)


def _track_face(src, ta, tb, c, step=0.2):
    """원본 [ta,tb] 동안 0.2초마다 얼굴 검출 → [(t, x, y, w, h)]. 기준 박스(box)에 가장 가까운 얼굴을 따라감."""
    import subprocess

    import cv2
    import numpy as np
    casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    ref = c.get("box")
    keys, t = [], ta
    while True:
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(src), "-frames:v", "1",
                              "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True).stdout
        img = np.frombuffer(raw, np.uint8).reshape(1080, 1920)
        fs = casc.detectMultiScale(img, 1.1, 5, minSize=(60, 60))
        if len(fs):
            if ref:
                rcx, rcy = ref[0] + ref[2] / 2, ref[1] + ref[3] / 2
                f = min(fs, key=lambda r: (r[0] + r[2] / 2 - rcx) ** 2 + (r[1] + r[3] / 2 - rcy) ** 2)
            else:
                f = max(fs, key=lambda r: r[2] * r[3])
            keys.append((t, *[float(v) for v in f]))
            ref = list(f)
        if t >= tb - 1e-3:
            break
        t = min(tb, t + step)
    return keys if len(keys) >= 2 else None


def _shot_geom(sh, iw, ih):
    """샷의 기본 크롭(원본 픽셀)과 확대 초점(패널 좌표)."""
    cx, cy, h = sh["crop"]
    h = min(h, ih)
    w = h * PW / PH
    if w > iw:
        w, h = iw, iw * PH / PW
    x0 = max(0, min(iw - w, cx - w / 2))
    y0 = max(0, min(ih - h, cy - h / 2))
    S = PW / w
    fx, fy = sh.get("focus", [cx, cy])
    return x0, y0, w, h, S, ((fx - x0) * S, (fy - y0) * S)


def render_edl(job: Path, edl_file: Path, cfg, out_name="sample.mp4"):
    job = Path(job).resolve()
    edl = read_json(edl_file)
    tmp = job / "edl_tmp"
    tmp.mkdir(exist_ok=True)
    words_src = read_json(job / "transcript_words.json")
    from .scenes import detect_cuts
    src_cuts = sorted(detect_cuts(job / "source.mp4", 0.25) if not (job / "cuts_fine.json").exists()
                      else read_json(job / "cuts_fine.json"))
    iw, ih = 1920, 1080
    S_ = cfg["subtitle"]
    dim = float(cfg["render"].get("narration_dim", 1.0))  # 1.0 = 어둡게 안 함
    top = cfg["layout"]["title_h"]
    seg_files, timeline, ass_ev, sfx_ev, log, sub_list = [], 0.0, [], [], [], []
    exp_items, exp_sfx = [], []  # CapCut 내보내기용 구조 정보 (edl_tmp/export.json)
    money_done = False  # 지폐 아이콘은 영상 전체에서 한 번만 (제품 매출 금액, 2026-11-10 사용자 규칙)

    def add(t0, t1, text, layer=3, style="Narr"):
        # ASS 시간은 0.01초 단위 → 30fps 프레임 경계(0.0333초)에 정확히 걸리도록 4ms 앞당겨 반올림
        ass_ev.append(f"Dialogue: {layer},{ass_time(max(0, t0 - 0.004))},{ass_time(max(0, t1 - 0.004))},{style},,0,0,0,,{text}")

    for n, it in enumerate(edl["items"]):
        wav, dur, wl, gain = _item_audio(job, it, cfg, words_src, tmp, n)
        wl = _snap_onsets(wav, wl, log, f"item{n}")
        # 30fps 프레임 경계로 길이를 맞춤 → 이어 붙일 때 그림이 자막·원보다 밀리는 누적 오차 방지
        dur = max(1, round((dur + it.get("tail", 0.0)) * 30)) / 30  # tail: 마지막 항목 뒤 그림·자막을 조금 더 잡아 둠(영상 끝 전용)
        wt = lambda k: 0.0 if k <= 0 else (wl[min(k, len(wl) - 1)][1] if wl else 0.0)
        # ---- 그림: 샷마다 시작 단어에서 컷
        shots = it["shots"]
        # 프레임 경계. at_t(항목 안 초)는 원본 컷 시점에 맞춰 크롭만 바꿀 때 (단어와 무관한 원본 편집점)
        starts = [0.0] + [round((sh["at_t"] if "at_t" in sh else max(0.0, wt(sh["at_word"]) - 0.03)) * 30) / 30
                          for sh in shots[1:]]
        ends = starts[1:] + [dur]
        inputs, fc = [], []
        for k, (sh, s0, s1) in enumerate(zip(shots, starts, ends)):
            if sh.get("src") == "sync":  # 말하는 사람이 화면에 나오는 샷: 시작 단어의 원본 시각부터 → 입모양 일치
                kw = sh.get("at_word", 0)
                sh = {**sh, "src": wl[kw][3] - (wl[kw][1] - s0), "sync_src": True}
            d = s1 - s0
            # 원본 컷 가드 (2026-11-09 개정: 정지 화면 금지 — 사용자가 '화면이 멈춤'을 싫어함)
            src0, speed, take = sh["src"], 1.0, d  # speed: 원본 1초를 몇 초로 늘려 보여 주는지
            if sh.get("hold"):  # 정지 화면 (예전 방식, 새 EDL 에서는 쓰지 않음)
                take = 1 / 30
            elif sh.get("sync_src") and not sh.get("file"):
                # 말하는 사람 샷: 시작/끝 0.3초 안에 원본 컷이 있으면 그 사이만 '살아 있는' 그림
                a_ = [c + 0.02 for c in src_cuts if src0 < c < src0 + 0.3]
                b_ = [c - 0.02 for c in src_cuts if src0 + d - 0.3 < c < src0 + d]
                s_live, e_live = (max(a_) if a_ else src0), (min(b_) if b_ else src0 + d)
                live = e_live - s_live
                if live < d - 1e-3:
                    f = d / live
                    clear = lambda x0, x1: not any(x0 < c < x1 for c in src_cuts)
                    if f <= 1.2:  # 살짝 느리게(최대 1.2배) 늘려 채움 → 입모양 차이가 서서히 0~0.25초
                        src0, take, speed = s_live, live, f
                        how = f"{f:.2f}배 느리게 늘림"
                    elif b_ and clear(e_live - d, e_live):  # 끝이 모자라면 그만큼 앞에서 시작
                        how = f"{src0 - (e_live - d):.2f}초 앞에서 시작"
                        src0 = e_live - d
                    elif a_ and clear(s_live, s_live + d):  # 시작이 모자라면 그만큼 뒤에서 시작
                        how = f"{s_live - src0:.2f}초 뒤에서 시작"
                        src0 = s_live
                    else:
                        src0, take, speed = s_live, live, f
                        how = f"{f:.2f}배 느리게 늘림(어쩔 수 없음)"
                    log.append(f"  ❚ item{n} shot{k}: 원본 컷이 샷 {'시작' if a_ else ''}{'끝' if b_ else ''}에 걸림 → {how} (정지 화면 없음)")
            elif not sh.get("file") and not sh.get("no_guard"):  # no_guard: 불꽃 등으로 가짜 컷이 많은 샷
                # 내레이션·일반 샷: 샷 안에 원본 컷이 있으면 0.3초짜리 다른 장면이 끼어 '깜빡임' → 컷 없는 구간으로 옮김
                if any(src0 < c < src0 + d for c in src_cuts):
                    bounds = [0.0] + sorted(src_cuts) + [1e9]
                    best = None
                    for lo_, hi_ in zip(bounds, bounds[1:]):
                        if hi_ - lo_ >= d + 0.08:
                            st = min(max(src0, lo_ + 0.04), hi_ - 0.04 - d)
                            if best is None or abs(st - src0) < abs(best - src0):
                                best = st
                    if best is not None:
                        src0 = best
                    else:
                        log.append(f"  ⚠ item{n} shot{k}: {d:.2f}초 동안 컷 없는 원본 구간이 없음")
            if abs(src0 - sh["src"]) > 1e-6:
                log.append(f"  ↔ item{n} shot{k}: 원본 컷 가드로 src {sh['src']:.2f} → {src0:.2f} "
                           f"(차이 {src0 - sh['src']:+.2f}s)")
                sh = {**sh, "src": src0}
            z0, z1 = sh.get("zoom", [1.0, 1.0])
            # 화질: 원본(유튜브 1080p, 약 1.3Mbps)을 너무 늘리면 뭉개짐 → 최종 확대 배율(크롭 늘림 × 줌)을 max_upscale 이하로
            mu = sh.get("max_upscale", cfg["render"].get("max_upscale", 1.4))  # 샷마다: 멀리 찍힌 말하는 사람 얼굴은 더 당겨야 할 때
            if PH / sh["crop"][2] * max(z0, z1) > mu:
                h_new = min(ih, PH * max(z0, z1) / mu)
                log.append(f"  ⇲ item{n} shot{k}: 확대 제한 크롭 높이 {sh['crop'][2]} → {h_new:.0f}px "
                           f"(배율 {PH / sh['crop'][2] * max(z0, z1):.2f} → {PH / h_new * max(z0, z1):.2f})")
                sh = {**sh, "crop": [sh["crop"][0], sh["crop"][1], h_new]}
            x0, y0, w0, h0, S, (fxo, fyo) = _shot_geom(sh, iw, ih)
            z = f"({z0}+({z1}-{z0})*t/{d:.3f})"
            inputs += ["-ss", f"{sh['src']:.3f}", "-t", f"{take + (0 if sh.get('hold') else 0.1):.3f}", "-i", str(job / sh.get("file", "source.mp4"))]
            nf = round(d * 30)  # 이 샷의 정확한 프레임 수
            fc.append(f"[{k}:v]" + (f"setpts=(PTS-STARTPTS)*{speed:.4f}," if speed > 1.0001 else "") + f"crop={int(w0)}:{int(h0)}:{int(x0)}:{int(y0)},"
                      f"scale=w='trunc({PW}*{z}/2)*2':h='trunc({PH}*{z}/2)*2':eval=frame:flags=lanczos,"
                      f"crop={PW}:{PH}:'{fxo:.1f}*({z}-1)':'{fyo:.1f}*({z}-1)',unsharp=5:5:0.35:5:5:0,"
                      # 내레이션(TTS) 구간은 화면을 살짝 어둡게 (참고: 셀 인사이트 쇼츠, 같은 인물·카메라에서 내레이션 때 23~40% 어두움)
                      + (f"colorchannelmixer=rr={dim}:gg={dim}:bb={dim}," if it["type"] == "narration" and dim < 0.999 else "")
                      + f"setsar=1,fps=30,format=yuv420p,"
                      f"tpad=stop_mode=clone:stop_duration={d + 0.2:.3f},"
                      f"trim=end_frame={nf},setpts=PTS-STARTPTS[v{k}]")
            if sh.get("sfx"):  # 샷이 바뀌는 프레임에 효과음 (컷 소리)
                sfx_ev.append((timeline + s0, sh["sfx"]))
            log.append(f"item{n} shot{k}: src {sh['src']:.2f}~{sh['src'] + d:.2f} → out {timeline + s0:.2f}~{timeline + s1:.2f}  ({sh.get('why', '')})")
            # 빨간 원: 대상 박스(원본 픽셀) → 이 샷의 크롭·확대를 반영한 화면 좌표, 확대에 맞춰 이동·확대
            c = sh.get("circle")
            if c:
                ca = max(s0, wt(c["at_word"]) - 0.03) if "at_word" in c else s0
                cb = min(s1, ca + c.get("hold", 1.5))  # 컷이 바뀌면 반드시 사라짐
                zt = lambda tt: z0 + (z1 - z0) * (tt - s0) / d
                pos = lambda tt, X, Y: (fxo + ((X - x0) * S - fxo) * zt(tt), fyo + ((Y - y0) * S - fyo) * zt(tt))
                # 대상 위치: 고정 박스 또는 얼굴 추적(track="face": 0.2초마다 검출 → 구간별 이동)
                keys = _track_face(job / "source.mp4", sh["src"] + (ca - s0), sh["src"] + (cb - s0), c) \
                    if c.get("track") == "face" else None
                if not keys:
                    keys = [(sh["src"] + (ca - s0), *c["box"]), (sh["src"] + (cb - s0), *c["box"])]
                pad = c.get("pad", 1.25)
                zi = S_["zoom_in_ms"]
                r0 = None
                pts = []
                for (ts, bx, by, bw, bh) in keys:
                    tt = s0 + (ts - sh["src"])  # 이 항목 안에서의 출력 시각
                    (px, py), z_ = pos(tt, bx + bw / 2, by + bh / 2 + c.get("dy", 0) * bh), zt(tt)
                    pts.append((tt, px, py + top, bw * S * z_ * pad / 2, bh * S * z_ * pad / 2))
                rx0, ry0 = pts[0][3], pts[0][4]
                for j in range(len(pts) - 1):  # 구간마다 이동·크기 보간
                    (ta, xa, ya, rxa, rya), (tb, xb, yb, rxb, ryb) = pts[j], pts[j + 1]
                    ms = max(1, int((tb - ta) * 1000))
                    appear = rf"\fscx0\fscy0\t(0,{zi},0.6,\fscx{100 * rxa / rx0:.1f}\fscy{100 * rya / ry0:.1f})" if j == 0 \
                        else rf"\fscx{100 * rxa / rx0:.1f}\fscy{100 * rya / ry0:.1f}"
                    body = (rf"{{\an5\move({xa:.0f},{ya:.0f},{xb:.0f},{yb:.0f})\p1\1a&HFF&"
                            rf"\3c{bgr('FF2E2E')}\bord9\shad0\blur0.6{appear}"
                            rf"\t({zi if j == 0 else 0},{ms},\fscx{100 * rxb / rx0:.1f}\fscy{100 * ryb / ry0:.1f})}}"
                            + _ellipse(rx0, ry0) + r"{\p0}")
                    add(timeline + ta, timeline + tb, body, layer=2)
                log.append(f"  ○ 원: '{c['target']}' — {c['why']} | {timeline + ca:.2f}~{timeline + cb:.2f}s, "
                           f"화면 중심 " + " → ".join(f"({p[1]:.0f},{p[2]:.0f})" for p in pts))
                if c.get("sfx"):
                    sfx_ev.append((timeline + ca, c["sfx"]))
        nv = len(shots)
        fc.append("".join(f"[v{k}]" for k in range(nv)) + f"concat=n={nv}:v=1:a=0,"
                  f"tpad=stop_mode=clone:stop_duration=0.2,trim=end_frame={round(dur * 30)},setpts=PTS-STARTPTS[vc]")
        if it.get("flash"):  # 색 번쩍임: 항목 시작에서 flash_alpha → 0 (flash_sec 동안)
            col = it["flash"]
            h = bgr(col)[2:-1]  # BBGGRR
            rgb = f"0x{h[4:6]}{h[2:4]}{h[0:2]}"
            fa, fs = edl.get("flash_alpha", 0.6), edl.get("flash_sec", 0.4)
            fc.append(f"color=c={rgb}:s={PW}x{PH}:d={dur:.3f}:r=30,format=gbrp[col];[vc]format=gbrp[vg];"
                      f"[vg][col]blend=shortest=1:all_expr='A+(B-A)*{fa}*max(0\\,1-T/{fs})',format=yuv420p[v]")
        else:
            fc.append("[vc]null[v]")
        inputs += ["-i", str(wav)]
        fc.append(f"[{nv}:a]aresample=48000,aformat=channel_layouts=stereo,volume={gain:.2f}dB,"
                  f"apad,atrim=duration={dur:.3f}[a]")
        f = tmp / f"item{n:02d}.mp4"
        ffmpeg(*inputs, "-filter_complex", ";".join(fc), "-map", "[v]", "-map", "[a]", "-t", f"{dur:.3f}",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "6", "-c:a", "aac", "-b:a", "320k", f)
        seg_files.append(f)
        real = float(run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=duration",
                          "-of", "csv=p=0", f]).strip().split()[0])
        if abs(real - dur) > 0.02:
            log.append(f"  ⚠ item{n} 실제 영상 길이 {real:.3f}s ≠ 계획 {dur:.3f}s")
        # ---- 자막 (전체 목록에 모았다가 마지막에 참고 영상 자막 문법으로 한꺼번에 그림)
        subs = [x if isinstance(x, dict) else {"text": x} for x in it["subs"]]
        if it["type"] == "narration":  # 어절 수로 시작 단어 계산
            k, sw = 0, []
            for s_ in subs:
                sw.append(k)
                k += len(tts_say(plain(s_["text"]).replace("|", " ")).split())  # | = 줄바꿈, ㅎㅎ 등은 어절 수에 안 셈
        else:
            sw = [s_.get("at_word", 0) for s_ in subs]
        st = [0.0] + [round(max(0.0, wt(k) - 0.03) * 30) / 30 for k in sw[1:]]
        # at_t: 말과 무관하게 항목 안 시각에 뜨는 자막 (예: 마지막 대사 끝난 뒤 따로 뜨는 '고정댓글 참조')
        st = [round(s_["at_t"] * 30) / 30 if "at_t" in s_ else t_ for s_, t_ in zip(subs, st)]
        for j, (s_, a) in enumerate(zip(subs, st)):
            b = st[j + 1] if j + 1 < len(st) else dur
            spans = money_green(parse_spans(s_["text"].replace("|", chr(10)), it.get("accent", "yellow")))  # 초록 = 돈 금액만
            sub_list.append({"a": timeline + a, "b": timeline + b, "spans": spans, "item": n, "text": s_["text"],
                             "krw": s_.get("krw", ""), "note": s_.get("note", ""), "solo": s_.get("solo", False),
                             "icon": "money" if s_.get("icon") == "money" and not money_done else ""})
            if s_.get("icon") == "money" and not money_done:  # 지폐 아이콘이 뜨는 프레임에 돈 소리 (카칭), 한 번만
                sfx_ev.append((timeline + a, s_.get("icon_sfx", "cash")))
                money_done = True
            log.append(f"  자막 {timeline + a:.2f}~{timeline + b:.2f}: {plain(s_['text'])} [{s_.get('anim', 'normal')}]")
        if it.get("sfx_word") is not None and it.get("sfx2"):
            # 자막·컷과 같은 계산(단어 시작 0.03초 전, 30fps 프레임 경계) → 소리·자막·그림이 같은 프레임에
            sfx_ev.append((timeline + round(max(0.0, wt(it["sfx_word"]) - 0.03) * 30) / 30, it["sfx2"]))
        if it.get("sfx"):
            sfx_ev.append((timeline + it.get("sfx_offset", 0.0), it["sfx"]))
        exp_items.append({"n": n, "type": it["type"], "t0": timeline, "dur": dur,
                          "shots": [[timeline + a_, timeline + b_, sh.get("why", ""), sh.get("file", "source.mp4")]
                                    for sh, a_, b_ in zip(shots, starts, ends)]})
        log.append(f"item{n} [{it['type']}] {timeline:.2f}~{timeline + dur:.2f}s  단어: "
                   + " ".join(f"{w}@{timeline + s:.2f}" for w, s, *_ in wl))
        timeline += dur

    # ---- 이어 붙이기 + 자막 + 효과음
    lst = tmp / "list.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in seg_files), encoding="utf-8")
    body = tmp / "body.mp4"
    # 재인코딩 concat (오디오 프라이밍·타임스탬프 누적 오차 없이)
    cin, cfc = [], []
    for k, p_ in enumerate(seg_files):
        cin += ["-i", str(p_)]
        cfc.append(f"[{k}:v][{k}:a]")
    ffmpeg(*cin, "-filter_complex", "".join(cfc) + f"concat=n={len(seg_files)}:v=1:a=1[v][a]", "-map", "[v]",
           "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "6", "-c:a", "aac", "-b:a", "320k", body)
    total = duration(body)
    sub_list = merge_short(sub_list, S_.get("min_sub_sec", 0.8))
    log += [f"  [최종 자막] {x['a']:.2f}~{x['b']:.2f} ({x['b'] - x['a']:.2f}s): {plain(x['text'])}" for x in sub_list]
    if S_.get("sub_anchor") == "bottom":  # 영상 패널 하단: 자막 덩어리의 아래 끝을 고정 (줄 수가 늘면 위로 자람)
        sub_pos, sub_an = (PW // 2, int(top + PH - S_.get("bottom_margin", 70))), 2
    else:
        sub_pos, sub_an = (PW // 2, int(top + PH * S_["center_ratio"])), 5
    for ly, t0, t1, sb in ref_sub_events(sub_list, cfg, sub_pos, sub_an):
        add(t0, t1, sb, ly + 1)
    # 돈 금액 자막 아래 지폐 이미지 (assets/money_icon.png, 사용자 지정 그림). 최종 합성 때 overlay 로 얹음
    icon = None
    ICON_W = 330
    for x in sub_list:
        if x.get("icon") == "money":
            lines = "".join(t for t, _ in x["spans"]).count("\n") + 1
            lh = S_["narr_size"] * 1.25
            top_y = sub_pos[1] + (lines * lh / 2 if sub_an == 5 else 0) + 25
            icon = (x["a"], x["b"], int(top_y))
            log.append(f"  💵 지폐 아이콘 {x['a']:.2f}~{x['b']:.2f}s (위쪽 y={top_y:.0f}): {plain(x['text'])}")
            break
    wm = cfg.get("watermark", {})
    if wm.get("text"):  # 영상 하단 워터마크 (잘 안 보이는 흰색)
        # 영상 패널 바로 아래 검은 바탕 (위쪽 제목처럼 검은 띠 위). y = 패널 아래 끝 + gap, 글자 위쪽 기준(an8)
        add(0, 99999, rf"{{\an8\pos({PW // 2},{top + PH + wm.get('gap', 22)})\fs{wm.get('size', 40)}\1c&HFFFFFF&"
                      rf"\alpha{wm.get('alpha', '&HA8&')}\bord0\shad0\blur0.5}}" + wm["text"], 20)
    head = _ass_head(cfg)
    T = edl["title_lines"]
    add(0, total, rf"{{\pos({PW // 2},{int(top - 30 - S_['title_size'] * 1.65)})\c{bgr(T[0]['color'])}\fs{S_['title_size']}}}" + T[0]["text"], 1, "Title")
    add(0, total, rf"{{\pos({PW // 2},{int(top - 30 - S_['title_size'] * 0.55)})\c{bgr(T[1]['color'])}\fs{S_['title_size']}}}" + T[1]["text"], 1, "Title")
    (tmp / "subs.ass").write_text("\n".join(head + ass_ev) + "\n", encoding="utf-8-sig")

    inputs, fc, mix = ["-i", body], [f"[0:v]pad={PW}:1920:0:{top}:color=black,ass=edl_tmp/subs.ass:fontsdir='{filter_path(ASSETS / 'fonts')}'[v]"], ["[0:a]"]
    used, used_files = [], set()
    # 효과음 크기: 참고 6편 측정(Demucs 분리) — 효과음 10ms RMS 최대가 목소리(60번째 백분위)보다 중앙값 -1.8dB.
    # 파일 피크로 맞추면 짧은 소리마다 체감 크기가 -11~+6dB 로 들쭉날쭉해서, 실제 10ms RMS 로 다시 맞춘다.
    vref = np.percentile((ve := _env_db(body))[ve > -45], 60)
    rel = cfg.get("sfx_mix", {}).get("rel_db", -1.8)
    opus_ev, level_ev = [], []
    engine = cfg["render"].get("sfx_engine", "level")
    if cfg["render"].get("no_sfx"):  # 효과음은 따로 믹스할 때 — 목소리만
        sfx_ev = []
    elif engine == "level" and sfx_ev:
        # 기본(2026-11-09~): 효과음마다 귀에 들리는 크기를 그 순간 목소리에 맞춤 (sfx_level.py)
        level_ev, sfx_ev = list(sfx_ev), []
    elif engine == "opus" and sfx_ev:
        # 기본(2026-11-08~): opus-sound-layer 실제 녹음으로 따로 믹스. 여기서는 목소리만 넣고 마지막에 소리를 바꿔 끼움
        from . import sfx_opus
        if sfx_opus.available():
            opus_ev, sfx_ev = list(sfx_ev), []
        else:
            log.append("  ⚠ opus-sound-layer 가 없어 예전 효과음 폴더로 믹스함 (ext/opus-sound-layer, uv 필요)")
    for k, (t, cat) in enumerate(sfx_ev, 1):
        # 같은 영상 안에서 같은 효과음 파일을 되도록 다시 쓰지 않음 (참고 영상은 소리가 다양)
        item = pick_sfx(cat, f"{job.name}-edl-{k}")
        for r in range(1, 12):
            if not item or item.get("pinned") or item["file"] not in used_files:
                break
            item = pick_sfx(cat, f"{job.name}-edl-{k}-{r}")
        if item:
            used_files.add(item["file"])
        if not item:
            continue
        lead = item.get("lead", 0.0)  # 파일 앞 무음을 잘라 소리가 사건(컷·원·자막)과 같은 프레임에 나게
        if t < 0:  # 앞당긴 효과음이 영상 시작 전으로 나가면 그만큼 소리 앞부분을 자름
            lead, t = lead - t, 0.0
        g =vref + rel - _env_db(item["file"]).max()
        used.append(f"{t:.2f}s {cat}: {item['name']} (앞무음 {lead * 1000:.0f}ms 제거, {g:+.1f}dB)")
        exp_sfx.append({"t": t, "cat": cat, "name": item["name"], "file": str(item["file"]), "lead": float(lead), "gain_db": float(g)})
        inputs += ["-i", item["file"]]
        # 꼬리 긴 효과음(휙·쿵 계열 최대 3초대)은 1.4초에서 0.3초 페이드로 끊음 → 다음 대사·효과음과 안 뭉개짐
        fc.append(f"[{k}:a]atrim=start={lead:.3f}:end={lead + 1.7:.3f},asetpts=PTS-STARTPTS,afade=t=out:st=1.4:d=0.3,"
                  f"aresample=48000,aformat=channel_layouts=stereo,volume={g:.1f}dB,"
                  f"adelay={int(t * 1000)}:all=1[s{k}]")
        mix.append(f"[s{k}]")
    if icon and (ASSETS / "money_icon.png").exists():  # 지폐 이미지: 살짝 떠오르며 나타남
        ia, ib, iy = icon
        n_in = sum(1 for v in inputs if v == "-i")
        inputs += ["-loop", "1", "-framerate", "30", "-t", f"{total:.3f}", "-i", str(ASSETS / "money_icon.png")]
        fc[0] = fc[0].replace("[v]", "[v0]")
        fc.append(f"[{n_in}:v]format=rgba,scale={ICON_W}:-2,fade=t=in:st={ia:.3f}:d=0.12:alpha=1[ic];"
                  f"[v0][ic]overlay=x=(W-w)/2:y='{iy}+40*max(0,1-(t-{ia:.3f})/0.2)':eval=frame:"
                  f"enable='between(t,{ia:.3f},{ib:.3f})'[v]")
    R = cfg["render"]
    master = R["loudness_lufs"] - (lufs_of(body) or R["voice_lufs"])
    fc.append(f"{''.join(mix)}amix=inputs={len(mix)}:normalize=0:duration=first,volume={master:.2f}dB,"
              f"alimiter=limit=0.89:attack=3:release=60:level=0[a]")
    ffmpeg(*inputs, "-filter_complex", ";".join(fc), "-map", "[v]", "-map", "[a]", "-c:v", "libx264",
           "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
           "-movflags", "+faststart", "-t", f"{total:.3f}", out_name, cwd=job)
    log += ["효과음: " + "; ".join(used)]
    if level_ev:
        from . import sfx_level
        tmp_out = job / ("_lvl_" + Path(out_name).name)
        exp_sfx, master, mlog = sfx_level.render(job, body, job / out_name, tmp_out, level_ev, total, tmp / "level",
                                                 cfg.get("sfx_mix", {}).get("master_lufs", -14.0))
        tmp_out.replace(job / out_name)
        log += mlog
    if opus_ev:
        from . import sfx_opus
        tmp_out = job / ("_opus_" + Path(out_name).name)
        exp_sfx, master, mlog = sfx_opus.render(job, body, job / out_name, tmp_out, opus_ev, total, tmp / "opus")
        tmp_out.replace(job / out_name)
        log += mlog
    write_json(tmp / "export.json", {
        "out": out_name, "total": float(total), "top": top, "panel": [PW, PH], "master_db": float(master),
        "items": exp_items, "sfx": exp_sfx, "title_lines": T,
        "subs": [{"a": x["a"], "b": x["b"], "spans": x["spans"], "krw": x.get("krw", ""), "note": x.get("note", ""),
                  "solo": x.get("solo", False), "item": x.get("item")} for x in sub_list],
        "circles": [e for e in ass_ev if e.startswith("Dialogue: 2,")],
        "ass_head": head, "sub_pos": list(sub_pos), "sub_an": sub_an})
    (job / "sample_log.txt").write_text("\n".join(log), encoding="utf-8")
    return job / out_name, total, log


def _ass_head(cfg):
    S = cfg["subtitle"]
    f = S["font"]
    st = "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"
    return ["[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920", "WrapStyle: 2",
            "ScaledBorderAndShadow: yes", "", "[V4+ Styles]", st,
            f"Style: Title,{f},{S['title_size']},&H00FFFFFF,&H000000FF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,0,3,5,0,0,0,1",
            f"Style: Narr,{f},{S['narr_size']},&H00FFFFFF,&H000000FF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1",
            "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
