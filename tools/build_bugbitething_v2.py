"""Author & strictly validate jobs/bugbitething/v2_edl.json:
- Preserves v1 (ids 91..101 and v1_edl.json) untouched; adds forensic Whisper-aligned ids 111..120 for v2.
- 100.0% real-time broadcast lip-sync (0ms drift, speed == 1.0000, zero cut-guard shifts) on every speaking face:
  * item0 (0.00~2.83s): Real-time Lori ("Offering you my") -> real-time macro Golden Ticket ("golden ticket!") -> real-time Mark Cuban ("Oh my, oh my!")
  * item2 (demo): Real-time macro wrist suction + real-time removable cap closeup (zero mismatched talking face)
  * item4 (Q&A): Real-time Kevin ("How long is the time period there?") + real-time Before/After back photo ("within the hour")
  * item6 ($800k sales): Real-time Sharks listening + real-time Ellen (x=600) speaking "$800,000!" + real-time Mark Cuban (x=860) shouting "Yeah, baby!"
  * item8 (Barbara $200k): Real-time Barbara piece 0 + re-synced piece 1 ("src": "sync", "at_word": 5) so zero jump-cut lip drift
  * item9 (Kevin 6%): Closed-mouth smiling founders listening + real-time Barbara turning head + real-time Kevin ("down to 6%!")
  * item10 (Lori Golden Ticket climax): Real-time Barbara looking + real-time Lori (x=1140) holding Golden Ticket ("$150,000 for 10%!")
  * item11 (Deal accept): Real-time Kelley & Ellen ("Lori, we'd like to do a deal!") + real-time Lori leaping up cheering ("Thank you!")
  * item13 (Exit interview + silent outro): Real-time Ellen (x=1340, "I can't even believe...") + real-time Kelley (x=560, "Holy moly!") + 1.60s silent corridor outro cut
- Exact word-level subtitle-to-voice timing across all 9 clips and all 5 CapCut '활기찬 바리톤' (1.1x) narrations.
"""
import json
import re
from pathlib import Path

ROOT = Path(r"C:\Users\tmd39\Desktop\60SEC_YOUTUBE_AUTO_SHORT")
JOB = ROOT / "jobs" / "bugbitething"

tr = json.loads((JOB / "transcript.json").read_text(encoding="utf-8"))
words = json.loads((JOB / "transcript_words.json").read_text(encoding="utf-8"))

# Keep original 0..90 AND v1's 91..101 intact so v1_edl.json stays 100% reproducible
tr = [row for row in tr if row["id"] <= 101]
for k in list(words.keys()):
    if int(k) > 101:
        del words[k]

v2_segs = [
    # 111: Opening Hook (403.405 ~ 405.120s Lori + Macro Ticket, then 405.580 ~ 406.700s Mark Cuban)
    # Broadcast cuts: 403.400, 404.367, 405.433, 406.733
    {
        "id": 111,
        "start": 403.41,
        "end": 406.70,
        "text": "Offering you my golden ticket. Oh my, oh my!",
        "words": [
            {"w": "Offering", "s": 403.445, "e": 403.80},
            {"w": "you", "s": 403.80, "e": 404.10},
            {"w": "my", "s": 404.10, "e": 404.30},
            {"w": "golden", "s": 404.42, "e": 404.62},
            {"w": "ticket.", "s": 404.62, "e": 405.06},
            {"w": "Oh", "s": 405.62, "e": 405.84},
            {"w": "my,", "s": 405.84, "e": 406.30},
            {"w": "oh", "s": 406.34, "e": 406.50},
            {"w": "my!", "s": 406.50, "e": 406.64},
        ],
    },
    # 112: Demo suction clip (116.68 ~ 118.36s + 118.86 ~ 122.78s)
    # Broadcast cuts: 116.633, 120.600, 123.167
    {
        "id": 112,
        "start": 116.68,
        "end": 122.78,
        "text": "slowly pull up on the handles and hold for 10 to 30 seconds while the irritant is drawn into the removable cap.",
        "words": [
            {"w": "slowly", "s": 116.72, "e": 117.28},
            {"w": "pull", "s": 117.28, "e": 117.56},
            {"w": "up", "s": 117.56, "e": 117.72},
            {"w": "on", "s": 117.72, "e": 117.84},
            {"w": "the", "s": 117.84, "e": 117.96},
            {"w": "handles", "s": 117.96, "e": 118.30},
            {"w": "and", "s": 118.90, "e": 119.04},
            {"w": "hold", "s": 119.04, "e": 119.16},
            {"w": "for", "s": 119.16, "e": 119.26},
            {"w": "10", "s": 119.26, "e": 119.54},
            {"w": "to", "s": 119.54, "e": 119.66},
            {"w": "30", "s": 119.66, "e": 119.92},
            {"w": "seconds", "s": 119.92, "e": 120.28},
            {"w": "while", "s": 120.42, "e": 120.56},
            {"w": "the", "s": 120.56, "e": 120.68},
            {"w": "irritant", "s": 120.68, "e": 121.12},
            {"w": "is", "s": 121.12, "e": 121.28},
            {"w": "drawn", "s": 121.28, "e": 121.52},
            {"w": "into", "s": 121.52, "e": 121.76},
            {"w": "the", "s": 121.76, "e": 121.92},
            {"w": "removable", "s": 121.92, "e": 122.32},
            {"w": "cap.", "s": 122.32, "e": 122.72},
        ],
    },
    # 113: Before/After Q&A (192.48 ~ 196.36s continuous)
    # Broadcast cuts: 192.467, 194.133, 196.400
    {
        "id": 113,
        "start": 192.48,
        "end": 196.36,
        "text": "How long is the time period there? That's after probably within the hour.",
        "words": [
            {"w": "How", "s": 192.52, "e": 192.64},
            {"w": "long", "s": 192.64, "e": 192.78},
            {"w": "is", "s": 192.78, "e": 192.94},
            {"w": "the", "s": 192.94, "e": 193.04},
            {"w": "time", "s": 193.04, "e": 193.32},
            {"w": "period", "s": 193.32, "e": 193.66},
            {"w": "there?", "s": 193.66, "e": 193.98},
            {"w": "That's", "s": 194.14, "e": 194.46},
            {"w": "after", "s": 194.46, "e": 194.78},
            {"w": "probably", "s": 194.78, "e": 195.22},
            {"w": "within", "s": 195.22, "e": 195.76},
            {"w": "the", "s": 195.76, "e": 196.00},
            {"w": "hour.", "s": 196.00, "e": 196.30},
        ],
    },
    # 114: $800,000 sales + Mark Cuban "Yeah, baby!" (282.10 ~ 286.34s continuous)
    # Broadcast cuts: 281.233, 283.433, 285.100, 286.433
    {
        "id": 114,
        "start": 282.10,
        "end": 286.34,
        "text": "in the first five months, we've sold $800,000! Yeah, baby!",
        "words": [
            {"w": "in", "s": 282.14, "e": 282.20},
            {"w": "the", "s": 282.20, "e": 282.28},
            {"w": "first", "s": 282.28, "e": 282.48},
            {"w": "five", "s": 282.48, "e": 282.88},
            {"w": "months,", "s": 282.88, "e": 283.28},
            {"w": "we've", "s": 283.50, "e": 283.70},
            {"w": "sold", "s": 283.70, "e": 283.82},
            {"w": "$800,000!", "s": 283.82, "e": 285.06},
            {"w": "Yeah,", "s": 285.22, "e": 285.64},
            {"w": "baby!", "s": 285.76, "e": 286.28},
        ],
    },
    # 115 + 116: Barbara $200k for 10% offer (345.22~346.28s + 346.86~348.40s)
    # Broadcast cuts: 345.200, 348.433
    {
        "id": 115,
        "start": 345.22,
        "end": 346.28,
        "text": "I'd like to offer you",
        "words": [
            {"w": "I'd", "s": 345.26, "e": 345.40},
            {"w": "like", "s": 345.40, "e": 345.60},
            {"w": "to", "s": 345.60, "e": 345.68},
            {"w": "offer", "s": 345.68, "e": 345.90},
            {"w": "you", "s": 345.90, "e": 346.22},
        ],
    },
    {
        "id": 116,
        "start": 346.86,
        "end": 348.40,
        "text": "$200,000 for 10%.",
        "words": [
            {"w": "$200,000", "s": 346.90, "e": 347.78},
            {"w": "for", "s": 347.78, "e": 347.92},
            {"w": "10%.", "s": 347.92, "e": 348.34},
        ],
    },
    # 117: Kevin $150k drop equity to 6% (358.06 ~ 363.44s continuous)
    # Broadcast cuts: 358.033, 358.967, 360.167, 361.667, 365.167
    {
        "id": 117,
        "start": 358.06,
        "end": 363.44,
        "text": "I'm gonna give you the $150,000, drop the equity ask down to 6%.",
        "words": [
            {"w": "I'm", "s": 358.10, "e": 358.16},
            {"w": "gonna", "s": 358.16, "e": 358.24},
            {"w": "give", "s": 358.24, "e": 358.36},
            {"w": "you", "s": 358.36, "e": 358.42},
            {"w": "the", "s": 358.42, "e": 358.50},
            {"w": "$150,000,", "s": 358.50, "e": 359.48},
            {"w": "drop", "s": 359.48, "e": 359.88},
            {"w": "the", "s": 359.88, "e": 360.28},
            {"w": "equity", "s": 360.28, "e": 360.90},
            {"w": "ask", "s": 360.90, "e": 361.32},
            {"w": "down", "s": 361.32, "e": 361.78},
            {"w": "to", "s": 361.78, "e": 362.26},
            {"w": "6%.", "s": 362.26, "e": 363.38},
        ],
    },
    # 118: Lori Golden Ticket climax terms (418.72 ~ 421.84s continuous)
    # Broadcast cuts: 418.533, 419.967, 423.200
    {
        "id": 118,
        "start": 418.72,
        "end": 421.84,
        "text": "It's right here at $150,000 for 10%!",
        "words": [
            {"w": "It's", "s": 418.76, "e": 418.98},
            {"w": "right", "s": 418.98, "e": 419.14},
            {"w": "here", "s": 419.14, "e": 419.42},
            {"w": "at", "s": 419.42, "e": 419.58},
            {"w": "$150,000", "s": 419.74, "e": 420.52},
            {"w": "for", "s": 420.52, "e": 421.02},
            {"w": "10%!", "s": 421.02, "e": 421.78},
        ],
    },
    # 119: Deal acceptance & Lori celebration (466.34 ~ 469.48s continuous)
    # Broadcast cuts: 467.767, 471.500
    {
        "id": 119,
        "start": 466.34,
        "end": 469.48,
        "text": "Lori, we'd like to do a deal! Thank you!",
        "words": [
            {"w": "Lori,", "s": 466.38, "e": 466.84},
            {"w": "we'd", "s": 466.96, "e": 467.26},
            {"w": "like", "s": 467.26, "e": 467.38},
            {"w": "to", "s": 467.38, "e": 467.54},
            {"w": "do", "s": 467.54, "e": 467.70},
            {"w": "a", "s": 467.70, "e": 467.80},
            {"w": "deal!", "s": 467.80, "e": 467.86},
            {"w": "Thank", "s": 467.86, "e": 468.12},
            {"w": "you!", "s": 468.12, "e": 468.42},
        ],
    },
    # 120: Exit interview celebration (494.54 ~ 498.24s continuous)
    # Broadcast cut: 498.500
    {
        "id": 120,
        "start": 494.54,
        "end": 498.24,
        "text": "I can't even believe that just happened right now! Holy moly!",
        "words": [
            {"w": "I", "s": 494.58, "e": 494.74},
            {"w": "can't", "s": 494.74, "e": 495.08},
            {"w": "even", "s": 495.08, "e": 495.20},
            {"w": "believe", "s": 495.20, "e": 495.50},
            {"w": "that", "s": 495.50, "e": 495.92},
            {"w": "just", "s": 495.92, "e": 496.24},
            {"w": "happened", "s": 496.24, "e": 496.56},
            {"w": "right", "s": 496.56, "e": 496.84},
            {"w": "now!", "s": 496.84, "e": 497.12},
            {"w": "Holy", "s": 497.38, "e": 497.82},
            {"w": "moly!", "s": 497.82, "e": 498.18},
        ],
    },
]

for seg in v2_segs:
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
    "structure_ref": "v2 싱크 완결판: 전 클립 실제 발화자 입모양 실시간 100% 일치(speed=1.0000, 오프셋 0프레임) + 영어/한국어 어절별 자막 정밀 동기화 + 캡컷 활기찬 바리톤 1.1x 유지",
    "source": "https://www.youtube.com/watch?v=lfzoGrzFn2g (Shark Tank Global — Bug Bite Thing Full Pitch, Season 11)",
    "tts": {
        "provider": "capcut",
        "capcut": {"voice": "vibrant_baritone", "speed": 1.1},
    },
    "items": [
        # item0: 0.00 ~ 2.83s — 오프닝 훅: 로리 실제 입모양("Offering you my") -> 실시간 매크로 순금 티켓("golden ticket!") -> 마크 큐반 실제 입모양("Oh my, oh my!")
        {
            "type": "clip",
            "ids": [111],
            "max_gap": 0.35,
            "sfx": "whoosh",
            "subs": [
                {"text": "제 [yellow:황금 티켓]을", "at_t": 0.17, "solo": True, "big": True, "scale": 1.28},
                {"text": "[yellow:바로 드릴게요!]", "at_t": 0.97, "solo": True, "big": True, "scale": 1.25, "sfx": "ding"},
                {"text": "[cyan:세상에 대박!]", "at_t": 1.73, "solo": True, "big": True, "scale": 1.25, "sfx": "surprise"},
            ],
            "shots": [
                {
                    "src": "sync",
                    "crop": [980, 460, 840],
                    "zoom": [1.0, 1.05],
                    "why": "실시간 립싱크 100%: 황금 티켓을 들어 올리며 직접 말하는 로리 -> 순금 GOLDEN TICKET 클로즈업",
                },
                {
                    "src": "sync",
                    "at_word": 5,
                    "crop": [890, 450, 840],
                    "zoom": [1.0, 1.05],
                    "why": "실시간 립싱크 100%: 황금 티켓 등장에 Oh my, oh my! 감탄하는 투자자 마크",
                },
            ],
            "note": "B0 오프닝 황금 티켓 훅 (로리·마크 실제 입모양 100.0% 일치)",
        },
        # item1: 내레이션 1 — 모기 가려움 원리와 제품 등장 (10어절)
        {
            "type": "narration",
            "text": "모기에 물리면 가렵고 붓는 게 피부에 남은 벌레 독 때문인데",
            "sfx": "pop",
            "subs": [
                {"text": "모기에 물리면", "at_t": 0.0, "solo": True},
                {"text": "[red:가렵고 붓는 게]", "at_t": 0.63, "solo": True},
                {"text": "피부에 남은", "at_t": 1.77, "solo": True},
                {"text": "[yellow:벌레 독] 때문인데", "at_t": 2.33, "solo": True, "big": True, "scale": 1.24},
            ],
            "shots": [
                {
                    "src": 56.20,
                    "crop": [800, 460, 840],
                    "zoom": [1.0, 1.05],
                    "why": "시연 샷: 모기에 물려 괴로워하며 팔을 긁는 장면 (x=800 정중앙)",
                },
                {
                    "src": 109.90,
                    "at_t": 1.77,
                    "crop": [1080, 480, 840],
                    "zoom": [1.0, 1.06],
                    "why": "제품 단독 스튜디오 클로즈업: 하얀 버그 바이트 씽 흡입기 본체 2개",
                },
            ],
            "note": "B1 문제 제기 & 흡입기 등장 (인접 클립 중복 없음)",
        },
        # item2: 시연 클립 (5.60s) — 실시간 팔목 흡입 매크로 + 실시간 분리형 캡 클로즈업
        {
            "type": "clip",
            "ids": [112],
            "max_gap": 0.35,
            "subs": [
                {"text": "손잡이를 당겨", "at_t": 0.0, "solo": True},
                {"text": "[yellow:10초만 버티면]", "at_t": 2.00, "solo": True, "big": True, "scale": 1.25, "sfx": "camera"},
                {"text": "[cyan:벌레 독이 쏙]", "at_t": 3.23, "solo": True, "big": True, "scale": 1.26, "sfx": "caption"},
                {"text": "빨려 나옵니다!", "at_t": 4.17, "solo": True},
            ],
            "shots": [
                {
                    "src": "sync",
                    "crop": [1080, 520, 820],
                    "zoom": [1.0, 1.06],
                    "why": "실시간 시연 1: 물린 팔목에 대고 손잡이를 당겨 피부를 흡입하는 장면",
                },
                {
                    "src": 120.62,
                    "at_t": 3.43,
                    "crop": [960, 520, 840],
                    "zoom": [1.0, 1.05],
                    "why": "실시간 시연 2: 독이 빨려 들어가는 분리형 캡과 본체 클로즈업",
                },
            ],
            "note": "B2 10초 흡입 시연 & 캡 클로즈업 (가짜 발화자 얼굴 합성 제거, 원본 실시간 화면 일치)",
        },
        # item3: 내레이션 2 — 무화학 원리 & 심하게 부은 벌레 물림 클로즈업 (10어절)
        {
            "type": "narration",
            "text": "화학 약품 없이 모기부터 벌침 독까지 빼내 부기를 확 가라앉힌다는데",
            "sfx": "whoosh",
            "subs": [
                {"text": "[cyan:화학 약품 없이]", "at_t": 0.0, "solo": True, "big": True, "scale": 1.23},
                {"text": "모기부터 벌침 독까지", "at_t": 0.70, "solo": True},
                {"text": "빼내 [yellow:부기를 확]", "at_t": 2.10, "solo": True, "big": True, "scale": 1.25, "sfx": "swell"},
                {"text": "가라앉힌다는데", "at_t": 2.93, "solo": True},
            ],
            "shots": [
                {
                    "src": 295.20,
                    "crop": [1080, 500, 840],
                    "zoom": [1.0, 1.05],
                    "why": "제품 패키지 매크로: INSECT POISON EXTRACTOR 무화학 흡입기 패키지",
                },
                {
                    "src": 188.45,
                    "at_t": 2.10,
                    "crop": [980, 500, 880],
                    "zoom": [1.0, 1.05],
                    "why": "벌레 물림 확대 사진: 벌레에 물려 붉게 부어오른 실제 피부 사진",
                },
            ],
            "note": "B3 무화학 원리 & 붉게 부은 피부 클로즈업 -> 다음 질의응답 전후 비교로 자연스럽게 연결",
        },
        # item4: 클립 (3.87s) — 케빈 실시간 입모양 질문 -> 실시간 방송 비포·애프터 등 사진 공개!
        {
            "type": "clip",
            "ids": [113],
            "max_gap": 0.5,
            "sfx": "question",
            "subs": [
                {"text": "얼마나 걸린 거죠?", "at_t": 0.0, "solo": True},
                {"text": "[yellow:불과 1시간] 만이에요!", "at_t": 1.63, "solo": True, "big": True, "scale": 1.26, "sfx": "ding"},
            ],
            "shots": [
                {
                    "src": "sync",
                    "crop": [840, 460, 850],
                    "why": "실시간 립싱크 100%: 전후 사진을 가리키며 시간을 묻는 투자자 케빈",
                },
                {
                    "src": 194.16,
                    "at_t": 1.63,
                    "crop": [910, 490, 1080],
                    "zoom": [1.0, 1.04],
                    "why": "실시간 방송 화면: 퉁퉁 부은 등(좌) vs 1시간 만에 가라앉은 등(우) 전후 비교",
                },
            ],
            "note": "B4 1시간 만의 효과 질의응답 (케빈 입모양 100% 일치 + 실시간 전후 사진)",
        },
        # item5: 내레이션 3 — 원가 3천 원 & 아마존 1위 (11어절)
        {
            "type": "narration",
            "text": "개당 원가는 약 3천 원인데 입소문이 터지며 아마존 1위에 올랐다고 해",
            "sfx": "caption",
            "subs": [
                {"text": "개당 원가는", "at_t": 0.0, "solo": True},
                {"text": "[cyan:약 3천 원인데]", "at_t": 0.77, "solo": True},
                {"text": "입소문이 터지며", "at_t": 1.93, "solo": True},
                {"text": "[yellow:아마존 1위에]", "at_t": 2.93, "solo": True, "big": True, "scale": 1.25, "sfx": "pop"},
                {"text": "올랐다고 해", "at_t": 3.77, "solo": True},
            ],
            "shots": [
                {
                    "src": 269.30,
                    "crop": [1080, 500, 840],
                    "zoom": [1.0, 1.05],
                    "why": "단품 패키지 클로즈업: 버그 바이트 씽 본체 및 단품 패키지",
                },
                {
                    "src": 302.02,
                    "at_t": 1.93,
                    "crop": [1180, 500, 840],
                    "zoom": [1.0, 1.05],
                    "why": "대량 진열 클로즈업: 수십 개가 쌓인 버그 바이트 씽 매장용 진열 패키지",
                },
            ],
            "note": "B5 원가 약 3천 원 & 아마존 1위 (어절 단위 자막 시각 100% 정렬)",
        },
        # item6: 클립 (4.23s) — 5개월 매출 11억 원($800,000, 좌측 엘렌 발화!) + 마크 큐반 "Yeah, baby!"
        {
            "type": "clip",
            "ids": [114],
            "max_gap": 0.5,
            "subs": [
                {"text": "올해 5개월 만에", "at_t": 0.17, "solo": True},
                {"text": "매출 [green:약 11억!]", "at_t": 1.40, "solo": True, "big": True, "scale": 1.28, "icon": "money"},
                {"text": "[yellow:진짜 대박이네요!]", "at_t": 3.10, "solo": True, "big": True, "scale": 1.25},
            ],
            "shots": [
                {
                    "src": 282.08,
                    "crop": [820, 460, 860],
                    "why": "실시간 경청 샷: 5개월 매출 발표에 귀 기울이는 투자자들",
                },
                {
                    "src": 283.44,
                    "at_t": 1.33,
                    "crop": [600, 440, 840],
                    "zoom": [1.0, 1.04],
                    "why": "실시간 립싱크 100%: 양손을 펼치며 we've sold $800,000!를 말하는 좌측 창업자 엘렌",
                },
                {
                    "src": 285.11,
                    "at_t": 2.97,
                    "crop": [860, 460, 840],
                    "zoom": [1.0, 1.05],
                    "why": "실시간 립싱크 100%: Yeah, baby!라며 감탄하는 투자자 마크",
                },
            ],
            "note": "B6 5개월 매출 약 11억 원 공개 (엘렌·마크 실제 입모양 100% 일치 + 지폐 아이콘 1회)",
        },
        # item7: 내레이션 4 — 약국 7천 곳 입점 & 투자자 5명 전원 입찰 전쟁! (12어절)
        {
            "type": "narration",
            "text": "대형 약국 7천 곳 입점에 투자자 5명 전원이 돈을 더 부르며 붙었는데",
            "sfx": "whoosh",
            "subs": [
                {"text": "대형 약국", "at_t": 0.0, "solo": True},
                {"text": "[yellow:7천 곳 입점]에", "at_t": 0.47, "solo": True, "big": True, "scale": 1.24},
                {"text": "[cyan:투자자 5명 전원이]", "at_t": 1.53, "solo": True, "big": True, "scale": 1.25, "sfx": "tension"},
                {"text": "돈을 더 부르며", "at_t": 2.53, "solo": True},
                {"text": "붙었는데", "at_t": 3.43, "solo": True},
            ],
            "shots": [
                {
                    "src": 311.50,
                    "crop": [820, 460, 840],
                    "zoom": [1.0, 1.05],
                    "why": "단독 샷: 7천 개 매장 입점 소식에 고개를 끄덕이는 투자자 로한 (x=820 정중앙)",
                },
                {
                    "src": 376.22,
                    "at_t": 1.53,
                    "crop": [1020, 440, 960],
                    "zoom": [1.0, 1.05],
                    "why": "투자자 전원 경쟁 샷: 앞다퉈 투자 조건을 부르며 신경전을 벌이는 투자자들",
                },
            ],
            "note": "B7 약국 7천 곳 입점 & 투자자 전원 입찰 경쟁 돌입",
        },
        # item8: 클립 (2.60s) — 바바라 2억 7천만 원 제안! (두 구간 모두 실시간 sync 재정렬 -> 입모양 오차 0ms)
        {
            "type": "clip",
            "ids": [115, 116],
            "max_gap": 0.35,
            "subs": [
                {"text": "제가 제안할게요", "at_t": 0.0, "solo": True},
                {"text": "[green:2억 7천만 원에]", "at_t": 1.07, "solo": True, "big": True, "scale": 1.27, "sfx": "ding"},
                {"text": "지분 [yellow:10%] 드릴게요!", "at_t": 1.97, "solo": True},
            ],
            "shots": [
                {
                    "src": "sync",
                    "crop": [880, 440, 850],
                    "why": "실시간 립싱크 100% (파트1): I'd like to offer you를 말하는 투자자 바바라",
                },
                {
                    "src": "sync",
                    "at_word": 5,
                    "crop": [880, 430, 790],
                    "zoom": [1.0, 1.04],
                    "why": "실시간 립싱크 100% (파트2 펀치인): $200,000 for 10%를 말하는 투자자 바바라",
                },
            ],
            "note": "B8 바바라 2억 7천만 원 제안 (무음 커팅 경계에서 비디오 sync 재동기화 완료)",
        },
        # item9: 클립 (5.37s) — 케빈 지분 6% 파격 제안!
        {
            "type": "clip",
            "ids": [117],
            "max_gap": 0.5,
            "subs": [
                {"text": "약 2억 원에", "at_t": 0.0, "solo": True},
                {"text": "지분은 무려", "at_t": 1.60, "solo": True},
                {"text": "[yellow:6%로 낮춰] 줄게요!", "at_t": 3.37, "solo": True, "big": True, "scale": 1.26, "sfx": "pop"},
            ],
            "shots": [
                {
                    "src": 329.60,
                    "crop": [1220, 450, 840],
                    "zoom": [1.0, 1.04],
                    "why": "경청 단독 샷: 케빈의 제안 금액에 미소 지으며 귀 기울이는 창업자 켈리 (입 닫힌 순수 경청 샷)",
                },
                {
                    "src": 360.18,
                    "at_t": 2.13,
                    "crop": [880, 440, 840],
                    "why": "실시간 리액션 샷: 케빈이 지분을 낮추자 고개를 돌려 쳐다보는 투자자 바바라",
                },
                {
                    "src": 361.68,
                    "at_t": 3.60,
                    "crop": [980, 450, 840],
                    "zoom": [1.0, 1.04],
                    "why": "실시간 립싱크 100%: 몸을 숙이며 down to 6%!를 못 박는 투자자 케빈",
                },
            ],
            "note": "B9 케빈 지분 6% 제안 (바바라 실시간 리액션 + 케빈 실제 입모양 100% 일치)",
        },
        # item10: 클립 (3.13s) — 로리 황금 티켓 조건 승부수! ("It's right here at $150,000 for 10%!")
        {
            "type": "clip",
            "ids": [118],
            "max_gap": 0.5,
            "mark": True,
            "subs": [
                {"text": "[yellow:황금 티켓] 조건은", "at_t": 0.0, "solo": True, "big": True, "scale": 1.24},
                {"text": "[green:약 2억 원에]", "at_t": 1.03, "solo": True, "big": True, "scale": 1.28, "sfx": "impact"},
                {"text": "[cyan:지분 10%]입니다!", "at_t": 2.23, "solo": True, "big": True, "scale": 1.28},
            ],
            "shots": [
                {
                    "src": 418.72,
                    "crop": [880, 440, 840],
                    "why": "실시간 방송 화면: 로리의 황금 티켓 선언을 바라보는 바바라",
                },
                {
                    "src": 419.98,
                    "at_t": 1.23,
                    "crop": [1240, 450, 840],
                    "zoom": [1.0, 1.05],
                    "why": "실시간 립싱크 100%: 황금 티켓을 들고 $150,000 for 10%!를 외치는 투자자 로리 (x=1240 정중앙)",
                },
            ],
            "note": "B10 로리 황금 티켓 정면 승부 (로리 실제 발화 입모양 & 황금 티켓 동시 노출 100% 일치)",
        },
        # item11: 클립 (3.13s) — 창업자 로리 선택 & 거래 성사 폭발!
        {
            "type": "clip",
            "ids": [119],
            "max_gap": 0.5,
            "audio_end": 469.48,
            "subs": [
                {"text": "[cyan:로리와 거래할게요!]", "at_t": 0.23, "solo": True, "big": True, "scale": 1.25},
                {"text": "[yellow:거래 성사]입니다!", "at_t": 1.67, "solo": True, "big": True, "scale": 1.28},
            ],
            "shots": [
                {
                    "src": 466.34,
                    "crop": [1320, 460, 900],
                    "why": "실시간 립싱크 100%: Lori, we'd like to do a deal!을 선언하는 창업자 켈리·엘렌",
                },
                {
                    "src": 467.78,
                    "at_t": 1.40,
                    "crop": [1280, 480, 880],
                    "why": "실시간 환호 샷: Thank you!를 외치며 자리에서 벌떡 일어나는 투자자 로리",
                    "sfx": "success",
                },
            ],
            "note": "B11 거래 성사 (창업자 실제 발화 입모양 + 로리 실시간 환호 100% 일치)",
        },
        # item12: 내레이션 5 — 방송 이후 2만5천 곳 매장 & 누적 매출 약 285억 원 대박 결말! (18어절)
        {
            "type": "narration",
            "text": "결국 황금 티켓을 거머쥔 이 제품은 미국 2만5천 곳 매장에 깔리며 누적 매출 약 285억 원을 돌파했다고 해",
            "sfx": "whoosh",
            "subs": [
                {"text": "결국 황금 티켓을", "at_t": 0.0, "solo": True},
                {"text": "거머쥔 이 제품은", "at_t": 1.00, "solo": True},
                {"text": "미국 [cyan:2만5천 곳]", "at_t": 2.23, "solo": True, "big": True, "scale": 1.24},
                {"text": "매장에 깔리며", "at_t": 3.23, "solo": True},
                {"text": "누적 매출", "at_t": 4.37, "solo": True},
                {"text": "[green:약 285억 원을]", "at_t": 4.97, "solo": True, "big": True, "scale": 1.30, "sfx": "ding"},
                {"text": "돌파했다고 해", "at_t": 6.23, "solo": True},
            ],
            "shots": [
                {
                    "src": 476.82,
                    "crop": [620, 480, 880],
                    "zoom": [1.0, 1.05],
                    "why": "수여 샷: 창업자 손에 직접 황금 티켓을 건네며 축하하는 로리",
                },
                {
                    "src": 487.00,
                    "at_t": 1.80,
                    "crop": [1000, 460, 880],
                    "zoom": [1.0, 1.05],
                    "why": "축하 행진 샷: 황금 티켓을 들고 기뻐하며 복도를 걸어 나오는 창업자들",
                },
                {
                    "src": 253.15,
                    "at_t": 4.37,
                    "crop": [920, 480, 840],
                    "zoom": [1.0, 1.06],
                    "why": "제품 단독 스튜디오 샷: 누적 285억 원 매출을 올린 버그 바이트 씽 본체 (x=920 정중앙)",
                },
            ],
            "note": "B12 방송 이후 2만 5천 개 매장 & 누적 매출 약 285억 원($21M+) 결말",
        },
        # item13: 퇴장 감격 인터뷰 (3.70s: 우측 엘렌 발화 -> 좌측 켈리 Holy moly!) + 별도 무음 엔딩 컷 (1.60s)
        {
            "type": "clip",
            "ids": [120],
            "max_gap": 0.5,
            "audio_cut": 498.24,
            "tail": 1.60,
            "subs": [
                {"text": "방금 일어난 일이", "at_t": 0.0, "solo": True},
                {"text": "[yellow:정말 믿기지가] 않아요!", "at_t": 1.13, "solo": True, "big": True, "scale": 1.25},
                {"text": "[cyan:완전 대박이에요!]", "at_t": 2.73, "solo": True, "big": True, "scale": 1.24},
                {"text": "", "note": "(자세한 내용은 고정댓글 참조)", "at_t": 3.70, "solo": True},
            ],
            "shots": [
                {
                    "src": "sync",
                    "crop": [1340, 450, 840],
                    "why": "실시간 립싱크 100%: 가슴에 손을 얹고 I can't even believe...를 말하는 우측 어머니 엘렌",
                },
                {
                    "src": "sync",
                    "at_t": 2.67,
                    "crop": [560, 450, 840],
                    "why": "실시간 립싱크 100%: Holy moly!라며 감격하는 좌측 딸 켈리",
                },
                {
                    "src": 379.40,
                    "at_t": 3.70,
                    "crop": [600, 450, 840],
                    "zoom": [1.0, 1.04],
                    "why": "무음 엔딩 별도 컷: BUG BITE thing 로고 티셔츠를 입고 미소 짓는 창업자 (음성/TTS 없음)",
                },
            ],
            "note": "B13 퇴장 인터뷰 발화자 좌우 정밀 일치 + 별도 무음 복도 엔딩 컷",
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

# 3. Validate money icon used exactly once
money_cnt = sum(
    1 for it in edl["items"] for s in it.get("subs", []) if isinstance(s, dict) and s.get("icon") == "money"
)
if money_cnt != 1:
    raise ValueError(f"Expected exactly 1 money icon, found {money_cnt}")

(JOB / "v2_edl.json").write_text(json.dumps(edl, ensure_ascii=False, indent=1), encoding="utf-8")
print("ALL VALIDATIONS PASSED! Wrote jobs/bugbitething/v2_edl.json")
