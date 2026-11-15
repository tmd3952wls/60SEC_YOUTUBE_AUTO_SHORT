"""셀 인사이트 스타일: 어려운 금융·투자 용어에 2단 보조 주석(note)을 자동으로 붙임.

세그먼트 자막에 용어가 처음 나왔는데 그 세그먼트에 note 가 비어 있으면 한 줄 뜻풀이를 채운다.
화면 과밀을 막으려고 한 영상당 최대 3개까지만.
"""
import re

FINANCE_NOTES = {
    "로열티": "(로열티: 제품 판매 시마다 지급하는 수수료)",
    "스톡옵션": "(스톡옵션: 성과 달성 시 지분을 주는 조건)",
    "번레이트": "(번레이트: 매달 빠져나가는 고정 현금 지출)",
    "멀티플": "(멀티플: 매출·이익 대비 몇 배로 회사 가치를 매겼는지)",
    "자문 지분": "(자문 지분: 조언·홍보 대가로 주는 지분)",
}
MAX_AUTO_NOTES = 3


def _seg_text(seg):
    if seg.get("type") == "narration":
        txt = seg.get("text", "")
    else:
        txt = " ".join(str(x) for x in seg.get("subs") or [])
    return re.sub(r"\[(\w+:)?|\]", "", txt)


def add_finance_notes(plan, max_notes=MAX_AUTO_NOTES):
    """plan['segments'] 에 note 를 제자리에서 채움. 붙인 개수를 반환."""
    seen, added = set(), 0
    for seg in plan.get("segments") or []:
        txt = _seg_text(seg)
        for term, note in FINANCE_NOTES.items():
            if term in seen or term not in txt:
                continue
            seen.add(term)  # '처음 등장'만 대상 (이미 note 가 있어도 그 용어는 소진)
            if not seg.get("note") and added < max_notes:
                seg["note"] = note
                added += 1
    return added
