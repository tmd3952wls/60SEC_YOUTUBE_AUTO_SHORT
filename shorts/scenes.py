"""원본의 컷(장면 전환) 위치 검출 + 구간 경계 보정.

구간 시작/끝 바로 옆에 원본 컷이 있으면, 0.x초짜리 다른 장면이 '번쩍' 끼어든다.
→ 내레이션 b-roll 은 컷이 없는 구간으로 옮기고, 대사 클립은 경계를 컷에 맞춰 다듬는다.
"""
import json
import re
import subprocess
from pathlib import Path


def detect_cuts(src: Path, threshold=0.3):
    cache = src.with_name("cuts.json")
    if cache.exists():
        return json.loads(cache.read_text())
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(src), "-an", "-vf",
                        f"scale=320:-1,select='gt(scene,{threshold})',showinfo", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    cuts = sorted(float(x) for x in re.findall(r"pts_time:([\d.]+)", r))
    cache.write_text(json.dumps(cuts))
    return cuts


def _cuts_in(cuts, a, b):
    return [c for c in cuts if a < c < b]


def place_broll(cuts, want, L, src_dur, min_shot):
    """want 근처에서 길이 L 짜리 창을 찾는다: 창 안에 min_shot 보다 짧은 조각이 생기지 않게.
    가장 좋은 건 컷이 아예 없는 창. 후보: want, want 이후/이전의 컷 지점들."""
    def score(a):
        if a < 0 or a + L > src_dur:
            return None
        inside = _cuts_in(cuts, a, a + L)
        bounds = [a] + inside + [a + L]
        shortest = min(y - x for x, y in zip(bounds, bounds[1:]))
        if shortest < min_shot:
            return None
        return (len(inside), abs(a - want))  # 컷 적을수록, 원래 위치에 가까울수록
    cands = [want] + [c + 0.04 for c in cuts if want - 8 < c < want + 12] + \
            [c - L - 0.04 for c in cuts if want - 8 < c < want + 12]
    best = min(((s, a) for a in cands if (s := score(a)) is not None), default=None)
    return best[1] if best else max(0.0, min(want, src_dur - L))


def broll_shots(cuts, start, L, src_dur, smin, smax):
    """내레이션 화면: start 부터 원본 샷들을 차례로 smin~smax 초씩 잘라 이어 붙여 길이 L 을 채운다.
    참고 영상처럼 1~1.5초마다 다른 장면으로 고르게 바뀌는 리듬."""
    cuts = sorted(cuts)
    nxt = lambda t: next((c for c in cuts if c > t + 0.02), src_dur)
    prv = lambda t: max([0.0] + [c for c in cuts if c <= t])
    # 시작이 샷 끝에 너무 가까우면(조각) 다음 샷부터
    a = start
    if nxt(a) - a < smin:
        a = nxt(a) + 0.04
    out, total, guard = [], 0.0, 0
    while total < L - 1e-3 and guard < 60:
        guard += 1
        if a >= src_dur - 0.1:
            a = max(0.0, prv(start) - 30)  # 원본 끝에 닿으면 앞쪽에서 다시
        end = nxt(a)
        take = min(end - a, smax, L - total)
        if take < smin and L - total > take + 1e-3:  # 너무 짧은 샷은 건너뜀
            a = end + 0.04
            continue
        out.append((a, a + take))
        total += take
        a = end + 0.04
    # 마지막 조각이 너무 짧으면 앞 조각에 붙이기 (같은 샷 안에서 늘릴 수 있을 때)
    if len(out) >= 2 and out[-1][1] - out[-1][0] < smin * 0.6:
        short = out.pop()
        pa, pb = out[-1]
        ext = min(short[1] - short[0], nxt(pa) - pb)
        out[-1] = (pa, pb + ext)
        if ext < short[1] - short[0] - 1e-3:
            out.append(short)
    return out


def trim_clip(cuts, a, b, speech_a, speech_b, min_shot, src_dur=1e9, max_speech_loss=0.25):
    """대사 클립 [a,b] 의 맨 앞/뒤에 min_shot 보다 짧은 샷 조각이 생기지 않게 경계를 조정.
    - 그 컷에서 자를 때 잃는 대사가 max_speech_loss 이하 → 컷에서 자름
    - 아니면 조각 샷이 min_shot 이 되도록 클립을 조금 늘림 (늘린 범위에 다른 컷이 없을 때)"""
    inside = _cuts_in(cuts, a, b)
    if inside:  # 앞쪽 조각
        c = inside[0]
        if c - a < min_shot:
            if c - speech_a <= max_speech_loss:
                a = c + 0.02
            elif not _cuts_in(cuts, c - min_shot, c):
                a = max(0.0, c - min_shot)
    inside = _cuts_in(cuts, a, b)
    if inside:  # 뒤쪽 조각
        c = inside[-1]
        if b - c < min_shot:
            if speech_b - c <= max_speech_loss:
                b = c - 0.02
            elif not _cuts_in(cuts, c, c + min_shot) and c + min_shot <= src_dur:
                b = c + min_shot
    return a, b
