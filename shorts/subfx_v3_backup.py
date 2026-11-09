"""네온 타자기 자막 (해외쇼쇼 스타일 분석 기반).

- 영상 패널 정중앙, 검은 외곽선 없음
- 어절별 색: 기본 흰색, [강조어] 는 이벤트마다 돌아가며 노랑/하늘/분홍/연두/주황
  [pink:강조어] 처럼 색을 직접 지정 가능. 줄 전체를 [ ] 로 감싸면 줄 전체가 색
- 글자가 한 글자씩 타이핑되며 나타나고, 같은 색 네온 빛이 크게 번졌다가 은은하게 남는다
"""
import re

PALETTE = ["yellow", "cyan", "pink", "green", "orange"]
NEON = {  # 네온용 밝은 색 (RGB)
    "white": "FFFFFF", "yellow": "FFE14D", "cyan": "4DF0FF", "pink": "FF6FC0",
    "green": "7CFF6B", "orange": "FFA640", "red": "FF4D5E", "blue": "5C8CFF", "purple": "C77DFF",
}


def bgr(name_or_hex):
    name_or_hex = name_or_hex.removesuffix("_s")  # "_s" = 작은 보조 줄(예: green_s 원화 환산)
    h = NEON.get(name_or_hex, name_or_hex).lstrip("#")
    return f"&H{h[4:6]}{h[2:4]}{h[0:2]}&".upper()


def parse_spans(text, accent):
    """'펌프로 [땅콩버터를]' → [(텍스트, 색이름)]. 대괄호가 덩어리 경계를 넘어 열려 있으면 이어받음."""
    spans, buf, color = [], "", "white"
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "[":
            if buf:
                spans.append((buf, color))
            buf = ""
            m = re.match(r"\[(\w+):", text[i:])
            if m and m.group(1) in NEON:
                color = m.group(1)
                i += len(m.group(0))
                continue
            color = accent
        elif ch == "]":
            if buf:
                spans.append((buf, color))
            buf, color = "", "white"
        else:
            buf += ch
        i += 1
    if buf:
        spans.append((buf, color))
    return spans


def open_state(text, was_open):
    """덩어리 끝에서 강조 괄호가 열려 있는지."""
    o = was_open
    for ch in text:
        if ch == "[":
            o = True
        elif ch == "]":
            o = False
    return o


def _ellipse(rx, ry):
    """(0,0)~(2rx,2ry) 박스에 꼭 맞는 타원 경로 (ASS 드로잉, 베지어 4개)."""
    k = 0.5523
    r = lambda v: f"{v:.1f}"
    return (f"m {r(rx)} 0 b {r(rx + k * rx)} 0 {r(2 * rx)} {r(ry - k * ry)} {r(2 * rx)} {r(ry)} "
            f"b {r(2 * rx)} {r(ry + k * ry)} {r(rx + k * rx)} {r(2 * ry)} {r(rx)} {r(2 * ry)} "
            f"b {r(rx - k * rx)} {r(2 * ry)} 0 {r(ry + k * ry)} 0 {r(ry)} "
            f"b 0 {r(ry - k * ry)} {r(rx - k * rx)} 0 {r(rx)} 0")


def circle_events(face_out, t0, t1, cfg):
    """말하는 사람 얼굴에 빨간 동그라미 (캡컷 확대 인 애니메이션과 같은 0.2초 등장)."""
    M = cfg["marks"]
    cx, cy, fw, fh = face_out
    rx, ry = fw * M["size_x"] / 2, fh * M["size_y"] / 2
    zi = cfg["subtitle"]["zoom_in_ms"]
    col = bgr(M["color"])
    body = (rf"{{\an5\pos({cx:.0f},{cy:.0f})\p1\1a&HFF&\3c{col}\bord{M['width']}\shad0\blur0.6"
            rf"\fscx0\fscy0\t(0,{zi},0.6,\fscx100\fscy100)}}" + _ellipse(rx, ry) + r"{\p0}")
    return [(t0, t1, "Narr", body, 2)]


FRAME = 1 / 30
SMALL = 0.68  # 보조 줄(원화 환산) 글자 크기 비율


def _fs(col, size):
    return rf"\fs{round(size * SMALL)}" if col.endswith("_s") else rf"\fs{size}"


def _colored(spans, alpha, size):
    out = []
    for txt, col in spans:
        out.append(rf"{{\1c{bgr(col)}\3c{bgr(col)}\alpha{alpha}{_fs(col, size)}}}" + txt.replace("\n", r"\N"))
    return "".join(out)


def _smear(spans, t0, t1, pos, layer, size, an=5):
    """등장 1프레임의 약한 가로 번짐.
    참고: 2jJoIbdciDY 는 1~2프레임 가로 번짐, QMJtjJz4M6w 는 일부 전환만 짧게 흐림, 0HbV-PW3ivw 는 대부분 즉시 교체.
    가독성 조정: 이동 폭 ±6~10px, 사본 3장, 약한 블러로 잔상이 남지 않게 (이전 ±42px·7장은 잔상처럼 보였음)."""
    x, y = pos
    evs = []
    for dx, a in ((-10, "&HC8&"), (0, "&H10&"), (10, "&HC8&")):
        evs.append((layer, t0, t1, rf"{{\an{an}\pos({x + dx},{y})\fscx104\bord1\blur1.5\shad0}}" + _colored(spans, a, size)))
    return evs


def merge_short(subs, min_dur=0.8, line_chars=14):
    """너무 짧게 지나가는 자막(min_dur 미만)은 같은 항목 안의 다음(없으면 앞) 자막과 의미 단위로 합친다.
    합친 글자가 길면 두 줄(| = 줄바꿈)로. 참고 영상 자막은 대부분 1초 안팎 이상 머문다."""
    out = [dict(s) for s in subs]
    changed = True
    while changed:
        changed = False
        for j, s in enumerate(out):
            # solo = 감탄사(와우! 등): 문장에 붙이지 않고 혼자 뜸 (사용자 요청 2026-11-06)
            if s["b"] - s["a"] >= min_dur or s.get("solo"):
                continue
            ok = lambda i: 0 <= i < len(out) and out[i].get("item") == s.get("item") and not out[i].get("solo")
            k = j + 1 if ok(j + 1) else (j - 1 if ok(j - 1) else None)
            if k is None:
                continue
            first, second = (s, out[k]) if k > j else (out[k], s)
            n = sum(len(t.strip()) for t, _ in first["spans"]) + sum(len(t.strip()) for t, _ in second["spans"])
            sep = [("\n", "white")] if n > line_chars else [(" ", "white")]
            krw = " · ".join(x for x in (first.get("krw"), second.get("krw")) if x)
            merged = {**first, "krw": krw, "b": second["b"], "spans": first["spans"] + sep + second["spans"],
                      "text": first.get("text", "") + (" | " if n > line_chars else " ") + second.get("text", "")}
            lo = min(j, k)
            out[lo:lo + 2] = [merged]
            changed = True
            break
    return out


def ref_sub_events(subs, cfg, pos, an=5):
    """자막 등장·교체 (참고 3편 비교 + 가독성 조정).
    - 등장: 약한 가로 번짐 1프레임 → 선명 (크기·위치·투명도 변화 없음, 강조어도 줄과 함께)
    - 퇴장: 다음 자막으로 즉시 교체 (번짐 없음)
    - 확대·바운스·페이드 없음."""
    F = FRAME
    evs = []
    sharp_cfg = {**cfg, "subtitle": {**cfg["subtitle"], "zoom_in_ms": 1, "zoom_from": 100}}
    for s in subs:
        a, b, sp = s["a"], s["b"], s["spans"]
        if s.get("krw"):  # 달러 금액 → 아래 줄에 작은 초록 글씨로 원화 환산
            sp = sp + [("\n", "white"), (s["krw"], "green_s")]
        evs += _smear(sp, a, a + F, pos, 5, cfg["subtitle"]["narr_size"], an)
        evs += neon_events(sp, a + F, b, sharp_cfg, pos=pos, an=an)
    return evs


def neon_events(spans, t0, t1, cfg, layer_base=3, pos=None, an=5):
    """한 자막 덩어리 → [(layer, start, end, text)].

    참고 영상 프레임 분석 결과를 그대로 옮김:
    - 긴 줄: 글자가 한 글자씩(약 1프레임 간격) 회색→흰색으로 빠르게 페이드 인 (타자기)
    - 짧은 감탄(≤ pop_max_chars): 작게 → 살짝 크게(오버슈트) → 제자리로 튀어나오는 팝
    - 빛: 크게 번지지 않는 '글자색 네온' + 가독성용 '어두운 그림자'. 등장 후엔 고정
    """
    S = cfg["subtitle"]
    head = (rf"\an{an}\pos({pos[0]},{pos[1]})" if pos else "")
    # 캡컷 [애니메이션 > 인 > 확대]: 0% → 100% 로 커지며 등장 (zoom_in_ms, 끝으로 갈수록 감속)
    zi = S["zoom_in_ms"]
    head += rf"\fscx{S['zoom_from']}\fscy{S['zoom_from']}\t(0,{zi},{S['zoom_accel']},\fscx100\fscy100)"

    def typed(alpha_to, color_tag):
        out = []
        for txt, col in spans:
            a_to = alpha_to(col) if callable(alpha_to) else alpha_to
            out.append("{" + color_tag(col) + _fs(col, S["narr_size"]) + rf"\alpha&HFF&\t(0,{max(1, zi // 2)},\alpha{a_to})}}")
            out.append(txt.replace("\n", r"\N"))
        return "".join(out)

    # ① 어두운 그림자 (밝은 배경에서도 읽히게)
    shadow = ("{" + head + rf"\shad0\bord{S['shadow_bord']}\blur{S['shadow_blur']}\3c&H000000&\1c&H000000&}}"
              + typed(S["shadow_alpha"], lambda c: ""))
    # ② 글자색 네온 빛 (좁고 선명하게)
    glow = ("{" + head + rf"\shad0\bord{S['glow_bord']}\blur{S['glow_blur']}}}"
            + typed(lambda c: S["glow_alpha_white"] if c == "white" else S["glow_alpha"],
                    lambda c: rf"\1c{bgr(c)}\3c{bgr(c)}"))
    # ③ 글자 본체
    text = ("{" + head + rf"\shad0\bord{S['text_bord']}\blur{S['text_blur']}}}"
            + typed("&H00&", lambda c: rf"\1c{bgr(c)}\3c{bgr(c)}"))
    return [(layer_base, t0, t1, shadow), (layer_base + 1, t0, t1, glow),
            (layer_base + 2, t0, t1, text)]
