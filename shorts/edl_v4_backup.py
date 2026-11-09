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
from .subfx import _ellipse, bgr, merge_short, neon_events, parse_spans, ref_sub_events
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


def _item_audio(job, it, cfg, words_src, tmp, idx):
    """항목 소리 파일 + 출력 기준 단어 시간 [(word, s, e)]."""
    R = cfg["render"]
    if it["type"] == "narration":
        wav = synth(plain(it["text"]), job / "tts", cfg)
        al = align_all([(str(wav), plain(it["text"]))], cfg)[str(wav)] or []
        wl = [(w["word"], w["start"], w["end"]) for w in al]
        return wav, duration(wav), wl, voice_gain(lufs_of(wav), R)
    # 원본 대사: 지정한 줄(ids)의 단어들, 단어 사이 긴 침묵은 '소리에서만' 잘라냄 (그림은 샷이 따로 채움)
    ws = [w for i in it["ids"] for w in words_src[str(i)]]
    if "word_range" in it:
        a, b = it["word_range"]
        ws = ws[a:b]
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
    top = cfg["layout"]["title_h"]
    seg_files, timeline, ass_ev, sfx_ev, log, sub_list = [], 0.0, [], [], [], []
    exp_items, exp_sfx = [], []  # CapCut 내보내기용 구조 정보 (edl_tmp/export.json)

    def add(t0, t1, text, layer=3, style="Narr"):
        # ASS 시간은 0.01초 단위 → 30fps 프레임 경계(0.0333초)에 정확히 걸리도록 4ms 앞당겨 반올림
        ass_ev.append(f"Dialogue: {layer},{ass_time(max(0, t0 - 0.004))},{ass_time(max(0, t1 - 0.004))},{style},,0,0,0,,{text}")

    for n, it in enumerate(edl["items"]):
        wav, dur, wl, gain = _item_audio(job, it, cfg, words_src, tmp, n)
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
            # 원본 컷 가드: 샷 시작/끝이 원본 컷에 걸쳐 1~3프레임짜리 다른 장면이 끼면 원본 샷 안으로 옮김
            src0 = sh["src"]
            # 입모양을 맞춘 샷은 옮기면 입이 어긋남 → 끼어드는 다른 장면(0.25초 이내)을 옆 프레임 정지로 덮음
            pre, keep = 0.0, d + 0.1
            if sh.get("sync_src") and not sh.get("file"):
                for c in src_cuts:
                    if src0 < c < src0 + 0.25:
                        pre = c + 0.02 - src0
                    elif src0 + d - 0.25 < c < src0 + d:
                        keep = c - 0.02 - src0
                if pre or keep < d:
                    log.append(f"  ❚ item{n} shot{k}: 원본 컷이 샷 {'시작' if pre else ''}{'끝' if keep < d else ''}에 걸림 → "
                               f"{pre:.2f}s/{max(0, d - keep):.2f}s 정지 화면으로 덮음 (입모양 유지)")
            # file: 방송 원본이 아닌 B-roll(실사용·리뷰 영상, 1920x1080·30fps로 맞춰 둔 것) → 원본 컷 가드 미적용
            for c in (src_cuts if not sh.get("file") and not sh.get("sync_src") else []):
                if src0 < c < src0 + 0.12:  # 시작 직후 컷 → 컷 뒤에서 시작
                    src0 = c + 0.04
                elif src0 + d - 0.15 < c < src0 + d:  # 끝 직전 컷 → 그만큼 앞에서 시작
                    if not any(src0 - (src0 + d - c) - 0.05 < c2 < src0 for c2 in src_cuts):
                        src0 = c - d - 0.04
            if abs(src0 - sh["src"]) > 1e-6:
                log.append(f"  ↔ item{n} shot{k}: 원본 컷 가드로 src {sh['src']:.2f} → {src0:.2f} "
                           f"(입모양 차이 {src0 - sh['src']:+.2f}s)")
                sh = {**sh, "src": src0}
            z0, z1 = sh.get("zoom", [1.0, 1.0])
            # 화질: 원본(유튜브 1080p, 약 1.3Mbps)을 너무 늘리면 뭉개짐 → 최종 확대 배율(크롭 늘림 × 줌)을 max_upscale 이하로
            mu = cfg["render"].get("max_upscale", 1.4)
            if PH / sh["crop"][2] * max(z0, z1) > mu:
                h_new = min(ih, PH * max(z0, z1) / mu)
                log.append(f"  ⇲ item{n} shot{k}: 확대 제한 크롭 높이 {sh['crop'][2]} → {h_new:.0f}px "
                           f"(배율 {PH / sh['crop'][2] * max(z0, z1):.2f} → {PH / h_new * max(z0, z1):.2f})")
                sh = {**sh, "crop": [sh["crop"][0], sh["crop"][1], h_new]}
            x0, y0, w0, h0, S, (fxo, fyo) = _shot_geom(sh, iw, ih)
            z = f"({z0}+({z1}-{z0})*t/{d:.3f})"
            inputs += ["-ss", f"{sh['src'] + pre:.3f}", "-t", f"{keep - pre:.3f}", "-i", str(job / sh.get("file", "source.mp4"))]
            nf = round(d * 30)  # 이 샷의 정확한 프레임 수
            fc.append(f"[{k}:v]crop={int(w0)}:{int(h0)}:{int(x0)}:{int(y0)},"
                      f"scale=w='trunc({PW}*{z}/2)*2':h='trunc({PH}*{z}/2)*2':eval=frame:flags=lanczos,"
                      f"crop={PW}:{PH}:'{fxo:.1f}*({z}-1)':'{fyo:.1f}*({z}-1)',unsharp=5:5:0.35:5:5:0,"
                      f"setsar=1,fps=30,format=yuv420p,"
                      f"tpad=start_mode=clone:start_duration={pre:.3f}:stop_mode=clone:stop_duration={d + 0.2:.3f},"
                      f"trim=end_frame={nf},setpts=PTS-STARTPTS[v{k}]")
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
                k += len(plain(s_["text"]).replace("|", " ").split())  # | = 자막 줄바꿈 (어절 수에 안 셈)
        else:
            sw = [s_.get("at_word", 0) for s_ in subs]
        st = [0.0] + [round(max(0.0, wt(k) - 0.03) * 30) / 30 for k in sw[1:]]
        for j, (s_, a) in enumerate(zip(subs, st)):
            b = st[j + 1] if j + 1 < len(st) else dur
            spans = parse_spans(s_["text"].replace("|", chr(10)), it.get("accent", "yellow"))
            sub_list.append({"a": timeline + a, "b": timeline + b, "spans": spans, "item": n, "text": s_["text"],
                             "krw": s_.get("krw", ""), "solo": s_.get("solo", False)})
            log.append(f"  자막 {timeline + a:.2f}~{timeline + b:.2f}: {plain(s_['text'])} [{s_.get('anim', 'normal')}]")
        if it.get("sfx_word") is not None and it.get("sfx2"):
            sfx_ev.append((timeline + max(0.0, wt(it["sfx_word"]) - 0.02), it["sfx2"]))
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
    if cfg["render"].get("no_sfx"):  # 효과음은 따로 믹스할 때 (opus-sound-layer 등) — 목소리만
        sfx_ev = []
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
    R = cfg["render"]
    master = R["loudness_lufs"] - (lufs_of(body) or R["voice_lufs"])
    fc.append(f"{''.join(mix)}amix=inputs={len(mix)}:normalize=0:duration=first,volume={master:.2f}dB,"
              f"alimiter=limit=0.89:attack=3:release=60:level=0[a]")
    ffmpeg(*inputs, "-filter_complex", ";".join(fc), "-map", "[v]", "-map", "[a]", "-c:v", "libx264",
           "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
           "-movflags", "+faststart", "-t", f"{total:.3f}", out_name, cwd=job)
    log += ["효과음: " + "; ".join(used)]
    write_json(tmp / "export.json", {
        "out": out_name, "total": float(total), "top": top, "panel": [PW, PH], "master_db": float(master),
        "items": exp_items, "sfx": exp_sfx, "title_lines": T,
        "subs": [{"a": x["a"], "b": x["b"], "spans": x["spans"], "krw": x.get("krw", ""),
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
