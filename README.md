# YOUTUBE_AUTO — 해외 예능 요약 쇼츠 자동 생성

```
원본(URL/파일) → 영어 전사(Whisper) → 대본 plan.json(LLM) → 내레이션 TTS → 렌더(1080x1920)
```

## 사용법
```bash
python make_short.py new "https://www.youtube.com/watch?v=..." --name 이름 --context "샤크탱크, 13살 창업자"
```
- `--start 120 --end 400` : 긴 에피소드에서 해당 구간만 사용 (전사 시간 단축)
- 결과: `jobs/이름/final.mp4`, 업로드용 제목·설명·태그는 `jobs/이름/upload.txt`

API 키가 없으면 **수동 모드**로 멈춥니다.
1. `jobs/이름/prompt.txt` 내용을 ChatGPT 또는 Claude 창에 붙여넣기
2. 받은 JSON을 `jobs/이름/plan.json` 으로 저장
3. `python make_short.py render jobs/이름`

대본(plan.json)을 고친 뒤에는 `render` 만 다시 실행하면 됩니다. TTS는 캐시를 재사용합니다.

## 설정
- `.env.example` 을 `.env` 로 복사한 뒤 키 입력
- `config.json`
  - `tts.provider`: `sapi`(윈도우 기본 음성, 테스트용) → `fish` 또는 `typecast` 로 변경
    - fish: `tts.fish.reference_id` 에 Fish Audio 보이스 모델 ID
    - typecast: `tts.typecast.voice_id` 에 `tc_...` 보이스 ID
  - `subtitle.font`: 굵은 폰트(G마켓 산스 Bold, Black Han Sans 등)를 `assets/fonts` 에 넣고 폰트 이름을 적기
  - `subtitle.dial_color`, `narr_color`: white / yellow / green / cyan / red / orange
  - `render.bgm_volume`, `sfx_volume`, `narration_original_volume`(내레이션 중 원본 소리, 0 = 음소거)
- `assets/bgm/` : BGM 파일(mp3/wav)을 넣으면 매번 무작위로 깔림 (내레이션·대사 나올 때 자동 덕킹)
- `assets/sfx/` : `whoosh` `pop` `ding` `boom` (.wav/.mp3). 같은 이름으로 넣으면 기본 합성음을 교체
- `prompts/script_prompt.md` : 대본 작성 규칙. 채널 톤을 바꾸려면 여기를 수정
