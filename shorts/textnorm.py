"""화면 자막 문자열 → TTS 발화 문자열 정규화 (가벼운 모듈: edl.py · tools/capcut_voice.py 공통).

두 곳이 같은 함수를 써야 CapCut 음성 파일 이름(md5(발화 문장))과 렌더러가 찾는 이름이 어긋나지 않는다.
"""
import re

# 자막에만 쓰는 재미 표현 (참고: 셀 인사이트 쇼츠 "ㄹㅇ 간단한 아이디어죠", "괜찮아용;;", "보시죠 ㅎ")
# TTS 에는 읽을 말로 바꾸거나 빼고, 자막 어절 수 셀 때도 같은 규칙으로 → 자막·목소리 싱크 유지
SAY = {"ㄹㅇ": "진짜", "ㅇㅋ": "오케이", "ㅈㄴ": "진짜", "ㅇㅈ": "인정"}

_PAREN = re.compile(r"\(([^()]*)\)")


def _drop_stage_direction(m):
    """'(비꼬는 중)', '(웃음)', '(*후일담은 댓글에)' 같은 화면 지문은 읽지 않음.
    '9.99달러(1만원)' 처럼 숫자가 든 괄호(단위·환산)는 그대로 둠."""
    inner = m.group(1).strip()
    if inner.startswith("*") or not re.search(r"\d", inner):
        return " "
    return m.group(0)


def tts_say(text):
    text = _PAREN.sub(_drop_stage_direction, str(text or ""))
    out = []
    for w in text.split():
        for k, v in SAY.items():  # 'ㄹㅇ' 단독뿐 아니라 'ㄹㅇ로' 같은 접두 형태도
            if w.startswith(k):
                w = v + w[len(k):]
                break
        w = re.sub(r"[ㄱ-ㅎㅏ-ㅣ;@~]+", "", w)  # ㅎㅎ ㅋㅋ ㅠㅠ ;; @ 같은 건 소리 내지 않음
        if w.strip():
            out.append(w)
    return " ".join(out)
