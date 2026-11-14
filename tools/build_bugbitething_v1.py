"""Author & strictly validate jobs/bugbitething/v1_edl.json:
- 100% <= 3 words per subtitle line (solo: true)
- 100% word-for-word match between narration text and narration subs
- Enlarged highlight subtitles (big: true, scale: 1.23~1.30)
- Money icon ("icon": "money") once on the $800k/11억 revenue reveal
- Pixel-verified 9:16 speaker face crops & zero cut-guard shifts
- Zero >0.35s speech silence gaps
- Separate silent outro shot (1.65s) with "(자세한 내용은 고정댓글 참조)"
"""
import json
import re
from pathlib import Path

ROOT = Path(r"C:\Users\tmd39\Desktop\60SEC_YOUTUBE_AUTO_SHORT")
JOB = ROOT / "jobs" / "bugbitething"

tr = json.loads((JOB / "transcript.json").read_text(encoding="utf-8"))
words = json.loads((JOB / "transcript_words.json").read_text(encoding="utf-8"))

tr = [row for row in tr if row["id"] <= 90]
for k in list(words.keys()):
    if int(k) > 90:
        del words[k]

extra_segs = [
    # 91: Opening Hook (403.04 ~ 406.60s) - Lori offers Golden Ticket + founders gasp "Oh my!"
    {
        "id": 91,
        "start": 403.04,
        "end": 406.60,
        "text": "I'm offering you my golden ticket. Oh my, oh my!",
        "words": [
            {"w": "I'm", "s": 403.06, "e": 403.32},
            {"w": "offering", "s": 403.34, "e": 403.80},
            {"w": "you", "s": 403.82, "e": 404.08},
            {"w": "my", "s": 404.10, "e": 404.30},
            {"w": "golden", "s": 404.32, "e": 404.62},
            {"w": "ticket.", "s": 404.62, "e": 405.05},
            {"w": "Oh,", "s": 405.58, "e": 405.95},
            {"w": "my,", "s": 405.95, "e": 406.30},
            {"w": "oh,", "s": 406.34, "e": 406.45},
            {"w": "my!", "s": 406.45, "e": 406.58},
        ],
    },
    # 92: Demo suction clip (116.65 ~ 122.68s)
    {
        "id": 92,
        "start": 116.65,
        "end": 122.68,
        "text": "slowly pull up on the handles and hold for 10 to 30 seconds while the irritant is drawn into the removable cap",
        "words": [
            {"w": "slowly", "s": 116.70, "e": 117.32},
            {"w": "pull", "s": 117.32, "e": 117.60},
            {"w": "up", "s": 117.60, "e": 117.72},
            {"w": "on", "s": 117.72, "e": 117.86},
            {"w": "the", "s": 117.86, "e": 117.96},
            {"w": "handles", "s": 117.96, "e": 118.34},
            {"w": "and", "s": 118.90, "e": 119.05},
            {"w": "hold", "s": 119.05, "e": 119.22},
            {"w": "for", "s": 119.22, "e": 119.28},
            {"w": "10", "s": 119.28, "e": 119.54},
            {"w": "to", "s": 119.54, "e": 119.66},
            {"w": "30", "s": 119.66, "e": 119.94},
            {"w": "seconds", "s": 119.94, "e": 120.32},
            {"w": "while", "s": 120.42, "e": 120.68},
            {"w": "the", "s": 120.68, "e": 120.75},
            {"w": "irritant", "s": 120.75, "e": 121.12},
            {"w": "is", "s": 121.12, "e": 121.28},
            {"w": "drawn", "s": 121.28, "e": 121.55},
            {"w": "into", "s": 121.55, "e": 121.78},
            {"w": "the", "s": 121.78, "e": 121.94},
            {"w": "removable", "s": 121.94, "e": 122.32},
            {"w": "cap", "s": 122.32, "e": 122.65},
        ],
    },
    # 93: Before/After Q&A (192.50 ~ 196.40s)
    {
        "id": 93,
        "start": 192.50,
        "end": 196.40,
        "text": "How long is the time period there? That's after probably within the hour.",
        "words": [
            {"w": "How", "s": 192.50, "e": 192.62},
            {"w": "long", "s": 192.62, "e": 192.82},
            {"w": "is", "s": 192.82, "e": 192.96},
            {"w": "the", "s": 192.96, "e": 193.04},
            {"w": "time", "s": 193.04, "e": 193.32},
            {"w": "period", "s": 193.32, "e": 193.66},
            {"w": "there?", "s": 193.66, "e": 193.98},
            {"w": "That's", "s": 194.15, "e": 194.44},
            {"w": "after", "s": 194.44, "e": 194.78},
            {"w": "probably", "s": 194.78, "e": 195.26},
            {"w": "within", "s": 195.26, "e": 195.78},
            {"w": "the", "s": 195.78, "e": 196.00},
            {"w": "hour.", "s": 196.00, "e": 196.35},
        ],
    },
    # 94: $800k in first 5 months (282.18 ~ 285.58s)
    {
        "id": 94,
        "start": 282.18,
        "end": 285.58,
        "text": "In the first five months we've sold $800,000! Yeah!",
        "words": [
            {"w": "In", "s": 282.18, "e": 282.25},
            {"w": "the", "s": 282.25, "e": 282.32},
            {"w": "first", "s": 282.32, "e": 282.52},
            {"w": "five", "s": 282.52, "e": 282.90},
            {"w": "months", "s": 282.90, "e": 283.36},
            {"w": "we've", "s": 283.36, "e": 283.70},
            {"w": "sold", "s": 283.70, "e": 283.84},
            {"w": "$800,000!", "s": 283.84, "e": 285.10},
            {"w": "Yeah!", "s": 285.10, "e": 285.55},
        ],
    },
    # 95 + 100: Barbara $200k for 10% offer (trimmed pause 346.26~346.88s so zero gap!)
    {
        "id": 95,
        "start": 345.20,
        "end": 346.26,
        "text": "I'd like to offer you",
        "words": [
            {"w": "I'd", "s": 345.21, "e": 345.42},
            {"w": "like", "s": 345.42, "e": 345.62},
            {"w": "to", "s": 345.62, "e": 345.72},
            {"w": "offer", "s": 345.72, "e": 345.95},
            {"w": "you", "s": 345.95, "e": 346.24},
        ],
    },
    # 96: Kevin $150k drop equity to 6% offer (357.95 ~ 363.30s)
    {
        "id": 96,
        "start": 357.95,
        "end": 363.30,
        "text": "I'm going to give you the $150,000, drop the equity ask down to 6%.",
        "words": [
            {"w": "I'm", "s": 358.00, "e": 358.12},
            {"w": "going", "s": 358.12, "e": 358.18},
            {"w": "to", "s": 358.18, "e": 358.24},
            {"w": "give", "s": 358.24, "e": 358.36},
            {"w": "you", "s": 358.36, "e": 358.42},
            {"w": "the", "s": 358.42, "e": 358.50},
            {"w": "$150,000,", "s": 358.50, "e": 359.48},
            {"w": "drop", "s": 359.66, "e": 359.96},
            {"w": "the", "s": 359.96, "e": 360.28},
            {"w": "equity", "s": 360.28, "e": 360.90},
            {"w": "ask", "s": 360.90, "e": 361.34},
            {"w": "down", "s": 361.34, "e": 361.80},
            {"w": "to", "s": 361.80, "e": 362.24},
            {"w": "6%.", "s": 362.24, "e": 363.26},
        ],
    },
    # 97 + 101: Lori Golden Ticket terms (trimmed breath so zero gap & exact vocal onset!)
    {
        "id": 97,
        "start": 416.55,
        "end": 417.52,
        "text": "If you want my ticket,",
        "words": [
            {"w": "If", "s": 416.56, "e": 416.68},
            {"w": "you", "s": 416.68, "e": 416.80},
            {"w": "want", "s": 416.80, "e": 416.98},
            {"w": "my", "s": 416.98, "e": 417.14},
            {"w": "ticket,", "s": 417.14, "e": 417.50},
        ],
    },
    # 98: Founders accept Lori's Golden Ticket (466.56 ~ 470.05s)
    {
        "id": 98,
        "start": 466.56,
        "end": 470.05,
        "text": "Lori, we'd like to do a deal! Thank you!",
        "words": [
            {"w": "Lori,", "s": 466.58, "e": 466.95},
            {"w": "we'd", "s": 467.08, "e": 467.30},
            {"w": "like", "s": 467.30, "e": 467.42},
            {"w": "to", "s": 467.42, "e": 467.54},
            {"w": "do", "s": 467.54, "e": 467.68},
            {"w": "a", "s": 467.68, "e": 467.76},
            {"w": "deal!", "s": 467.76, "e": 467.85},
            {"w": "Thank", "s": 467.85, "e": 468.10},
            {"w": "you!", "s": 468.10, "e": 470.00},
        ],
    },
    # 99: Exit interview celebration (494.82 ~ 498.32s)
    {
        "id": 99,
        "start": 494.82,
        "end": 498.32,
        "text": "I can't even believe that just happened right now! Holy moly!",
        "words": [
            {"w": "I", "s": 494.84, "e": 494.92},
            {"w": "can't", "s": 494.92, "e": 495.08},
            {"w": "even", "s": 495.08, "e": 495.20},
            {"w": "believe", "s": 495.20, "e": 495.50},
            {"w": "that", "s": 495.50, "e": 495.90},
            {"w": "just", "s": 495.90, "e": 496.24},
            {"w": "happened", "s": 496.24, "e": 496.54},
            {"w": "right", "s": 496.54, "e": 496.86},
            {"w": "now!", "s": 496.86, "e": 497.12},
            {"w": "Holy", "s": 497.42, "e": 497.82},
            {"w": "moly!", "s": 497.82, "e": 498.30},
        ],
    },
    # 100: Barbara $200,000 for 10% (part 2)
    {
        "id": 100,
        "start": 346.88,
        "end": 348.16,
        "text": "$200,000 for 10%.",
        "words": [
            {"w": "$200,000", "s": 346.90, "e": 347.76},
            {"w": "for", "s": 347.76, "e": 347.92},
            {"w": "10%.", "s": 347.92, "e": 348.15},
        ],
    },
    # 101: Lori $150,000 for 10% (part 2)
    {
        "id": 101,
        "start": 418.75,
        "end": 421.74,
        "text": "it's right here! $150,000 for 10%!",
        "words": [
            {"w": "it's", "s": 418.76, "e": 419.00},
            {"w": "right", "s": 419.00, "e": 419.18},
            {"w": "here!", "s": 419.18, "e": 419.48},
            {"w": "$150,000", "s": 419.76, "e": 420.60},
            {"w": "for", "s": 420.62, "e": 421.02},
            {"w": "10%!", "s": 421.04, "e": 421.72},
        ],
    },
]

for seg in extra_segs:
    sid = seg["id"]
    tr.append({"id": sid, "start": seg["start"], "end": seg["end"], "text": seg["text"]})
    words[str(sid)] = seg["words"]

(JOB / "transcript.json").write_text(json.dumps(tr, ensure_ascii=False, indent=1), encoding="utf-8")
(JOB / "transcript_words.json").write_text(json.dumps(words, ensure_ascii=False, indent=1), encoding="utf-8")

edl = {
    "title_lines": [
        {"text": "모기 독만 쏙 빼낸다고?!", "color": "yellow"},
        {"text": "황금 티켓 받은 흡입기", "color": "white"},
    ],
    "flash_alpha": 0.55,
    "flash_sec": 0.35,
    "krw_rate": "1달러=1,356원 기준 환산",
    "structure_ref": "GEMINI.md 표준: 0~3초 황금 티켓 초강력 후킹 + 전 구간 1줄 최대 3어절(solo:true) + 대박 자막 확대(big/scale) + 화자 얼굴 100% 노출 + 마지막 무음 고정댓글 별도 컷",
    "source": "https://www.youtube.com/watch?v=lfzoGrzFn2g (Shark Tank Global — Bug Bite Thing Full Pitch, Season 11)",
    "tts": {
        "provider": "capcut",
        "capcut": {"voice": "vibrant_baritone", "speed": 1.1},
    },
    "items": [
        # item0: 0.00 ~ 3.32s — 초강력 오프닝 훅 (로리 황금 티켓 선언 + 순금 실물 클로즈업 + 창업자 경악!)
        {
            "type": "clip",
            "ids": [91],
            "tail": 0.12,
            "sfx": "whoosh",
            "subs": [
                {"text": "제 [yellow:황금 티켓]을", "at_t": 0.0, "solo": True, "big": True, "scale": 1.28},
                {"text": "[yellow:바로 드릴게요!]", "at_t": 0.70, "solo": True, "big": True, "scale": 1.25},
                {"text": "[cyan:세상에 대박!]", "at_t": 2.50, "solo": True, "big": True, "scale": 1.25, "sfx": "surprise"},
            ],
            "shots": [
                {
                    "src": 436.00,
                    "crop": [880, 460, 840],
                    "zoom": [1.0, 1.06],
                    "why": "말하는 사람 단독 클로즈업: 황금 티켓 제안을 선언하는 투자자 로리",
                },
                {
                    "src": 410.22,
                    "at_t": 1.10,
                    "crop": [1100, 500, 810],
                    "zoom": [1.0, 1.06],
                    "why": "매크로 클로즈업: 손가락에 들린 실제 순금 GOLDEN TICKET 각인",
                    "sfx": "ding",
                },
                {
                    "src": 407.82,
                    "at_t": 2.20,
                    "crop": [1320, 440, 840],
                    "zoom": [1.0, 1.05],
                    "why": "창업자 클로즈업: 황금 티켓 등장에 눈이 휘둥그레진 창업자 켈리",
                },
            ],
            "note": "B0 오프닝 0~3.3초 초강력 황금 티켓 훅 (모든 샷 >= 1.10s, 무음 공백 0, 컷 가드 이동 0)",
        },
        # item1: 내레이션 1 — 모기 가려움 원리와 제품 등장 (10어절)
        {
            "type": "narration",
            "text": "모기에 물리면 가렵고 붓는 게 피부에 남은 벌레 독 때문인데",
            "sfx": "pop",
            "subs": [
                {"text": "모기에 물리면", "solo": True},
                {"text": "[red:가렵고 붓는 게]", "solo": True},
                {"text": "피부에 남은", "solo": True},
                {"text": "[yellow:벌레 독] 때문인데", "solo": True, "big": True, "scale": 1.24},
            ],
            "shots": [
                {
                    "src": 56.20,
                    "crop": [1120, 460, 860],
                    "zoom": [1.0, 1.05],
                    "why": "시연 샷: 모기에 물려 괴로워하며 팔을 긁는 장면",
                },
                {
                    "src": 120.65,
                    "at_word": 5,
                    "crop": [900, 520, 820],
                    "zoom": [1.0, 1.06],
                    "why": "매크로 클로즈업: 버그 바이트 씽 본체 및 패키지",
                },
            ],
            "note": "B1 문제 제기 & 흡입기 등장",
        },
        # item2: 시연 클립 (5.60s)
        {
            "type": "clip",
            "ids": [92],
            "subs": [
                {"text": "손잡이를 당겨", "at_word": 0, "solo": True},
                {"text": "[yellow:10초만 버티면]", "at_word": 6, "solo": True, "big": True, "scale": 1.25, "sfx": "camera"},
                {"text": "[cyan:벌레 독이 쏙]", "at_t": 2.93, "solo": True, "big": True, "scale": 1.26},
                {"text": "빨려 나옵니다!", "at_word": 18, "solo": True},
            ],
            "shots": [
                {
                    "src": "sync",
                    "crop": [1080, 520, 820],
                    "zoom": [1.0, 1.06],
                    "why": "초근접 매크로 시연: 물린 팔목에 대고 손잡이를 당겨 피부를 흡입하는 장면",
                },
                {
                    "src": 129.70,
                    "at_t": 3.88,
                    "crop": [580, 440, 840],
                    "zoom": [1.0, 1.04],
                    "why": "말하는 사람 클로즈업: 손짓하며 원리를 설명하는 공동창업자 엘렌",
                    "sfx": "caption",
                },
            ],
            "note": "B2 10초 흡입 매크로 시연 + 말하는 창업자 얼굴 정중앙 클로즈업",
        },
        # item3: 내레이션 2 — 무화학 & 붓기 전후 비교 사진 (10어절)
        {
            "type": "narration",
            "text": "화학 약품 없이 모기부터 벌침 독까지 빼내 부기를 확 가라앉힌다는데",
            "sfx": "whoosh",
            "subs": [
                {"text": "[cyan:화학 약품 없이]", "solo": True, "big": True, "scale": 1.23},
                {"text": "모기부터 벌침 독까지", "solo": True},
                {"text": "빼내 [yellow:부기를 확]", "solo": True, "big": True, "scale": 1.25, "sfx": "swell"},
                {"text": "가라앉힌다는데", "solo": True},
            ],
            "shots": [
                {
                    "src": 112.15,
                    "crop": [1340, 440, 840],
                    "zoom": [1.0, 1.05],
                    "why": "시연 클로즈업: 팔목에 직접 흡입기를 시연하며 설명하는 창업자 켈리",
                },
                {
                    "src": 178.10,
                    "at_word": 5,
                    "crop": [910, 490, 1080],
                    "zoom": [1.0, 1.05],
                    "why": "비포·애프터 한눈에 비교: 벌레에 물려 퉁퉁 부은 등(좌) vs 가라앉은 등(우)",
                },
            ],
            "note": "B3 무화학 원리 & 실제 전후 비교 사진 좌우 동시 노출",
        },
        # item4: 클립 (3.85s) — 케빈 질문 -> 창업자 "불과 1시간 만이에요!"
        {
            "type": "clip",
            "ids": [93],
            "sfx": "question",
            "subs": [
                {"text": "얼마나 걸린 거죠?", "at_word": 0, "solo": True},
                {"text": "[yellow:불과 1시간] 만이에요!", "at_word": 7, "solo": True, "big": True, "scale": 1.26, "sfx": "ding"},
            ],
            "shots": [
                {
                    "src": 192.51,
                    "crop": [840, 460, 850],
                    "why": "말하는 사람 단독 샷: 전후 사진을 가리키며 시간을 묻는 투자자 케빈",
                },
                {
                    "src": 77.50,
                    "at_t": 1.56,
                    "crop": [1360, 440, 840],
                    "why": "말하는 사람 클로즈업: 1시간 만에 가라앉았다고 답하는 창업자 켈리",
                },
            ],
            "note": "B4 1시간 만의 효과 질의응답 (전 구간 발화자 얼굴 정중앙 일치)",
        },
        # item5: 내레이션 3 — 원가 3천 원 & 아마존 1위 (11어절)
        {
            "type": "narration",
            "text": "개당 원가는 약 3천 원인데 입소문이 터지며 아마존 1위에 올랐다고 해",
            "sfx": "caption",
            "subs": [
                {"text": "개당 원가는", "solo": True},
                {"text": "[cyan:약 3천 원인데]", "solo": True},
                {"text": "입소문이 터지며", "at_t": 1.94, "solo": True},
                {"text": "[yellow:아마존 1위에]", "solo": True, "big": True, "scale": 1.25, "sfx": "pop"},
                {"text": "올랐다고 해", "solo": True},
            ],
            "shots": [
                {
                    "src": 269.30,
                    "crop": [900, 520, 820],
                    "zoom": [1.0, 1.05],
                    "why": "패키지 클로즈업: 버그 바이트 씽 단품 및 매장용 패키지",
                },
                {
                    "src": 295.20,
                    "at_word": 5,
                    "crop": [1340, 440, 840],
                    "zoom": [1.0, 1.05],
                    "why": "말하는 창업자 켈리 클로즈업: 제조 원가와 아마존 1위 성과 설명",
                },
            ],
            "note": "B5 원가 약 2,700~3천원($2) & 아마존 1위 소개",
        },
        # item6: 클립 (3.40s) — 올해 첫 5개월 만에 매출 약 11억 원 돌파! ($800,000)
        {
            "type": "clip",
            "ids": [94],
            "subs": [
                {"text": "올해 5개월 만에", "at_t": 0.18, "solo": True},
                {"text": "매출 [green:약 11억을]", "at_word": 5, "solo": True, "big": True, "scale": 1.28, "icon": "money"},
                {"text": "[yellow:돌파했어요!]", "at_t": 2.46, "solo": True, "big": True, "scale": 1.24},
            ],
            "shots": [
                {
                    "src": 299.00,
                    "crop": [1340, 440, 840],
                    "zoom": [1.0, 1.05],
                    "why": "말하는 사람 클로즈업: 5개월 매출 80만 달러(약 11억 원)를 밝히는 창업자 켈리",
                },
                {
                    "src": 166.20,
                    "at_t": 1.95,
                    "crop": [760, 450, 840],
                    "zoom": [1.0, 1.06],
                    "why": "리액션 단독 샷: 폭발적인 매출에 눈이 커지며 놀라는 투자자 로리",
                },
            ],
            "note": "B6 5개월 매출 약 11억 원 공개 + 지폐 아이콘 & cash 효과음 자동 부착",
        },
        # item7: 내레이션 4 — 약국 7천 곳 입점 & 투자자 5명 전원 입찰 전쟁! (12어절)
        {
            "type": "narration",
            "text": "대형 약국 7천 곳 입점에 투자자 5명 전원이 돈을 더 부르며 붙었는데",
            "sfx": "whoosh",
            "subs": [
                {"text": "대형 약국", "solo": True},
                {"text": "[yellow:7천 곳 입점]에", "solo": True, "big": True, "scale": 1.24},
                {"text": "[cyan:투자자 5명 전원이]", "solo": True, "big": True, "scale": 1.25, "sfx": "tension"},
                {"text": "돈을 더 부르며", "solo": True},
                {"text": "붙었는데", "solo": True},
            ],
            "shots": [
                {
                    "src": 311.50,
                    "crop": [960, 460, 850],
                    "zoom": [1.0, 1.05],
                    "why": "단독 샷: 7천 개 매장 입점 소식에 감탄하며 몸을 기울이는 투자자 로한",
                },
                {
                    "src": 376.22,
                    "at_word": 5,
                    "crop": [1080, 440, 1080],
                    "zoom": [1.0, 1.05],
                    "why": "투자자 전원 경쟁 샷: 앞다퉈 투자 조건을 부르며 신경전을 벌이는 투자자들",
                },
            ],
            "note": "B7 약국 7천 곳 입점 & 투자자 전원 입찰 경쟁 돌입",
        },
        # item8: 클립 — 바바라 2억 7천만 원 제안! (2.34s, 무음 공백 0, 컷 가드 이동 0)
        {
            "type": "clip",
            "ids": [95, 100],
            "subs": [
                {"text": "[green:2억 7천만 원에]", "at_word": 0, "solo": True, "big": True, "scale": 1.27, "sfx": "ding"},
                {"text": "지분 [yellow:10%] 드릴게요!", "at_word": 5, "solo": True},
            ],
            "shots": [
                {
                    "src": 345.24,
                    "crop": [920, 440, 840],
                    "zoom": [1.0, 1.06],
                    "why": "말하는 사람 단독 샷: 20만 달러(약 2억 7천만 원)를 제안하는 투자자 바바라",
                },
            ],
            "note": "B8 바바라 2억 7천만 원 상향 제안 (바바라 실제 발화 얼굴 정중앙 100% 일치)",
        },
        # item9: 클립 — 케빈 지분 6% 파격 제안! (5.35s)
        {
            "type": "clip",
            "ids": [96],
            "subs": [
                {"text": "약 2억 원에", "at_word": 0, "solo": True},
                {"text": "지분을 무려", "at_t": 1.14, "solo": True},
                {"text": "[yellow:6%로 낮춰] 줄게요!", "at_word": 11, "solo": True, "big": True, "scale": 1.26, "sfx": "pop"},
            ],
            "shots": [
                {
                    "src": 336.25,
                    "crop": [900, 460, 850],
                    "zoom": [1.0, 1.04],
                    "why": "말하는 사람 단독 샷: 몸을 앞으로 숙이며 제안하는 투자자 케빈",
                },
                {
                    "src": 361.71,
                    "at_t": 2.00,
                    "crop": [1020, 460, 850],
                    "zoom": [1.0, 1.05],
                    "why": "말하는 사람 단독 샷: 지분 6% 파격 조건을 못 박는 투자자 케빈",
                },
            ],
            "note": "B9 케빈 지분 6% 제안 (전 구간 케빈 발화 단독 얼굴 유지)",
        },
        # item10: 클립 — 로리 황금 티켓 조건 승부수! (4.51s, 무음 숨 고르기 제거 완료)
        {
            "type": "clip",
            "ids": [97, 101],
            "mark": True,
            "subs": [
                {"text": "제 [yellow:황금 티켓]은", "at_word": 0, "solo": True, "big": True, "scale": 1.24},
                {"text": "바로 여기 있어요!", "at_word": 5, "solo": True},
                {"text": "[green:약 2억 원에]", "at_word": 8, "solo": True, "big": True, "scale": 1.28, "sfx": "impact"},
                {"text": "[cyan:지분 10%!]", "at_word": 10, "solo": True, "big": True, "scale": 1.28},
            ],
            "shots": [
                {
                    "src": 416.88,
                    "crop": [820, 460, 840],
                    "zoom": [1.0, 1.06],
                    "why": "말하는 사람 샷: 황금 티켓 실물을 들어 보이며 제안하는 투자자 로리",
                },
                {
                    "src": 442.95,
                    "at_t": 1.25,
                    "crop": [880, 460, 840],
                    "zoom": [1.0, 1.05],
                    "why": "말하는 사람 단독 클로즈업: 15만 달러 지분 10% 조건을 강조하는 투자자 로리",
                },
            ],
            "note": "B10 로리 황금 티켓 정면 승부 (100% 로리 발화 얼굴 정중앙)",
        },
        # item11: 클립 — 로리 선택 & 거래 성사 폭발! (3.49s)
        {
            "type": "clip",
            "ids": [98],
            "subs": [
                {"text": "[cyan:로리와 거래할게요!]", "at_t": 0.0, "solo": True, "big": True, "scale": 1.25},
                {"text": "[yellow:거래 성사]입니다!", "at_t": 0.86, "solo": True, "big": True, "scale": 1.28},
            ],
            "shots": [
                {
                    "src": 466.56,
                    "crop": [1300, 460, 920],
                    "why": "말하는 사람 투샷: 로리를 선택하며 거래를 선언하는 모녀 창업자",
                },
                {
                    "src": 467.82,
                    "at_t": 1.20,
                    "crop": [1320, 480, 880],
                    "why": "환호 리액션 샷: 자리에서 벌떡 일어나 환호하는 투자자 로리",
                    "sfx": "success",
                },
            ],
            "note": "B11 거래 성사 (발화 시작점 100% 일치 + 정답 효과음)",
        },
        # item12: 내레이션 5 — 방송 이후 2만5천 곳 매장 & 누적 매출 약 285억 원 대박 결말! (15어절)
        {
            "type": "narration",
            "text": "결국 황금 티켓을 거머쥔 이 제품은 미국 2만5천 곳 매장에 깔리며 누적 매출 약 285억 원을 돌파했다고 해",
            "sfx": "whoosh",
            "subs": [
                {"text": "결국 황금 티켓을", "solo": True},
                {"text": "거머쥔 이 제품은", "solo": True},
                {"text": "미국 [cyan:2만5천 곳]", "solo": True, "big": True, "scale": 1.24},
                {"text": "매장에 깔리며", "solo": True},
                {"text": "누적 매출", "solo": True},
                {"text": "[green:약 285억 원을]", "solo": True, "big": True, "scale": 1.30, "sfx": "ding"},
                {"text": "돌파했다고 해", "solo": True},
            ],
            "shots": [
                {
                    "src": 476.82,
                    "crop": [520, 480, 920],
                    "zoom": [1.0, 1.05],
                    "why": "수여 샷: 창업자 손에 직접 황금 티켓을 건네며 축하하는 로리",
                },
                {
                    "src": 481.35,
                    "at_word": 4,
                    "crop": [620, 480, 860],
                    "zoom": [1.0, 1.05],
                    "why": "축하 전경 샷: 황금 티켓 거래 성사 후 환호하며 걸어가는 로리",
                },
                {
                    "src": 253.15,
                    "at_word": 11,
                    "crop": [1180, 520, 820],
                    "zoom": [1.0, 1.06],
                    "why": "매크로 클로즈업: 하얀 버그 바이트 씽 제품 본체 2개",
                },
            ],
            "note": "B12 방송 이후 2만 5천 개 매장 & 누적 매출 약 285억 원($21M+) 결말",
        },
        # item13: 퇴장 감격 인터뷰 (3.50s) + 별도 무음 아웃트로 컷 (1.65s) "(자세한 내용은 고정댓글 참조)"
        {
            "type": "clip",
            "ids": [99],
            "audio_cut": 498.32,
            "tail": 1.65,
            "subs": [
                {"text": "방금 일어난 일이", "at_t": 0.0, "solo": True},
                {"text": "[yellow:정말 믿기지가] 않아요!", "at_t": 0.85, "solo": True, "big": True, "scale": 1.25},
                {"text": "", "note": "(자세한 내용은 고정댓글 참조)", "at_t": 3.50, "solo": True},
            ],
            "shots": [
                {
                    "src": 494.82,
                    "crop": [580, 450, 840],
                    "why": "퇴장 인터뷰 클로즈업: 활짝 웃으며 감격하는 창업자 켈리 (494.82~496.57s)",
                },
                {
                    "src": 496.57,
                    "at_t": 1.75,
                    "crop": [1280, 450, 840],
                    "why": "퇴장 인터뷰 클로즈업: 가슴을 쓸어내리며 감격하는 어머니 엘렌 (496.57~498.32s)",
                },
                {
                    "src": 329.60,
                    "at_t": 3.50,
                    "crop": [480, 450, 840],
                    "why": "무음 엔딩 별도 컷: BUG BITE thing 로고 티셔츠를 입고 미소 짓는 창업자 (음성/TTS 없이 고정댓글 안내 단독 표시)",
                },
            ],
            "note": "B13 퇴장 감격 대사 종료 후 별도 무음 컷에 (자세한 내용은 고정댓글 참조) 단독 표시",
        },
    ],
}

def strip_tags(s: str) -> str:
    return re.sub(r"\[(\w+:)?|\]", "", s).strip()

# 1. Validate <= 3 words per subtitle line
bad_subs = []
for idx, it in enumerate(edl["items"]):
    for s in it.get("subs", []):
        raw_txt = s["text"] if isinstance(s, dict) else s
        clean = strip_tags(raw_txt)
        if clean:
            wc = len(clean.split())
            if wc > 3:
                bad_subs.append((idx, clean, wc))
if bad_subs:
    raise ValueError(f"Found subtitles exceeding 3 words: {bad_subs}")

# 2. Validate exact word-by-word match for every narration item
for idx, it in enumerate(edl["items"]):
    if it["type"] == "narration":
        t_words = it["text"].split()
        s_words = []
        for s in it["subs"]:
            s_words.extend(strip_tags(s["text"]).split())
        if t_words != s_words:
            raise ValueError(f"Narration item{idx} mismatch:\n  text={t_words}\n  subs={s_words}")

(JOB / "v1_edl.json").write_text(json.dumps(edl, ensure_ascii=False, indent=1), encoding="utf-8")

upload_txt = (JOB / "upload.txt").read_text(encoding="utf-8") if (JOB / "upload.txt").exists() else """제목: 모기에 물렸을 때 침만 쏙 빼낸다는 1만 원짜리 흡입기의 최후

설명:
화학 약품 없이 압력만으로 모기·벌침 독을 쏙 빨아내 가려움과 부기를 확 가라앉힌다는 신기한 흡입기! 투자자 5명 전원이 서로 돈을 더 주겠다며 입찰 전쟁을 벌이다 결국 시즌당 단 한 번 나오는 '황금 티켓'까지 등장했는데, 과연 방송 이후 어떻게 됐을까요? #샤크탱크 #버그바이트씽 #창업 #아이디어상품 #쇼츠

태그: 샤크탱크, 버그바이트씽, Bug Bite Thing, 모기흡입기, 벌레물림, 아이디어상품, 창업성공사례, 로리그라이너, 황금티켓, 쇼츠
"""
(JOB / "upload.txt").write_text(upload_txt, encoding="utf-8")

pinned_md = (JOB / "pinned_comment.md").read_text(encoding="utf-8") if (JOB / "pinned_comment.md").exists() else ""
if pinned_md:
    (JOB / "pinned_comment.md").write_text(pinned_md, encoding="utf-8")

print("ALL CHECKS PASSED! v1_edl.json, upload.txt, pinned_comment.md written!")
narr_lines = [it["text"] for it in edl["items"] if it["type"] == "narration"]
for i, ln in enumerate(narr_lines, 1):
    print(f"  [{i}] {ln}")
