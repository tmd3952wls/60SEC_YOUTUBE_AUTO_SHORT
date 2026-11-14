# 60SEC_YOUTUBE_AUTO_SHORT — Gemini & Antigravity (`agy`) Workspace Rules

이 저장소는 해외 창업·투자 예능 요약 60초 쇼츠 자동 제작 파이프라인(`shorts/`, `editor/`, `make_short.py`)에 **완전 자동 효과음 디렉터(`auto_sfx/`)**, **웹 에디터 원클릭 유튜브 신규 작업 생성(`editor/new_job_worker.py`)**, **CapCut 활기찬 바리톤(1.1x) 내레이션 연동**, **실시간 효과음 리믹서(`editor/`)** 를 통합한 워크스페이스입니다. [Google Antigravity 공식 규칙 사양](https://antigravity.google/docs/rules/)에 따라 이 파일은 YAML frontmatter 없이 항상 활성(`always_on`) 규칙으로 동작합니다.

## 1. 과금 걱정 없는 3단계 연출 엔진 (`SFX_DIRECTOR_BACKEND`)

별도 API 요금 부담 없이 운영할 수 있도록 3가지 모드를 모두 지원합니다:

1. **`local-free` (100% 오프라인 무료 엔진 · 0원)**: API 키 없이 EDL 대본 강조색(`[green:...]` 매출 금액, `[red:...]` 위기), 장면 전환(`shots`), 10ms 음성 시작점, FFmpeg 씬 체인지를 결합해 0.5초 만에 정밀 큐시트를 생성합니다.
2. **`agy-cli` (Antigravity 구독 연동 · 0원)**: 로컬 PC의 [Antigravity CLI (`agy -p`)](https://antigravity.google/docs/cli/best-practices/) 로그인 계정을 헤드리스로 호출해 별도 토큰 과금 없이 대본(`shorts/script.py`)과 효과음 큐시트(`auto_sfx/cuesheet.py`)를 생성합니다.
3. **`gemini-api` ([Google GenAI SDK](https://googleapis.github.io/python-genai/) 멀티모달)**: [Google AI Studio 가격 정책](https://ai.google.dev/gemini-api/docs/pricing)에 따라 결제 카드(Cloud Billing)를 연결하지 않은 프로젝트 키는 Free Tier(`Free of charge`) 한도 내에서 무료로 동작하며, `gemini-2.5-flash` 기본값과 분당 호출 안전 간격(`--free-tier-safe`)이 내장되어 있습니다.

## 2. 터미널 없는 웹 에디터 올인원 제작 흐름 (`run_editor.bat` / `editor/server.py`)

1. **원클릭 신규 작업 시작 (`+ 새 작업` 모달 → `POST /api/jobs/create` → `editor/new_job_worker.py`)**
   - 상단바 **`+ 새 작업`** 버튼에 유튜브 URL(또는 로컬 영상 경로)과 제목·주제 힌트(`/`로 2줄 분리 가능)만 입력하면 `yt-dlp` 다운로드(1920x1080 30fps 정규화) → Whisper 음성 전사 → 어절 타임스탬프 정렬 → 한국어 대본 작성(`claude-cli` / `agy-cli` / API / 0원 스타터 초안) → `v1_edl.json` 변환까지 완료한 뒤 자동으로 편집 화면을 엽니다.
2. **내레이션 목소리 (`CapCut 활기찬 바리톤` · `vibrant_baritone` 1.1배속)**
   - 상단바 **`바리톤 음성`** 버튼에서 미준비 내레이션 문장만 모은 CapCut 프로젝트를 생성(`make`)하고, 읽힌 음성을 1.1배속으로 수확(`harvest`)해 즉시 렌더링·미리보기에 사용합니다.
3. **해외쇼쇼 강도·밀도 프리셋 · ★ 즐겨찾기 · 2초 오디오 리믹스**
   - **AI 효과음** 탭에서 `깔끔형` / `해외쇼쇼 표준` / `타격감 강조형` 프리셋을 선택하고 **`소리만 다시 입히기 (2초 완성)`**(`-c:v copy`)으로 `full_vN_sfx1.mp4`를 무손실 생성합니다. **효과음 폴더** 탭에서 별표(★)를 찍은 효과음(`assets/sfx_favorites.json`)은 큐시트 매칭 시 최우선 채택됩니다.
4. **원클릭 CapCut 프로젝트 내보내기 (`CapCut 내보내기`)**
   - 리믹스된 효과음 트랙(`--sfx-video`), 활기찬 바리톤 내레이션, 배달의민족주아체 자막, 트랙별 샷을 분리된 CapCut 편집 프로젝트로 즉시 생성합니다.

## 3. 로컬 2,869개 효과음 카탈로그 & 브랜드 불변 규칙

- **로컬 효과음 폴더**: `LOCAL_SFX_DIR=C:\Users\tmd39\Desktop\효과음\효과음2869개` (`assets/sfx_catalog.json` 증분 캐시).
- **사람 목소리 간섭 차단**: 내레이션·원본 대사 중에는 사람 감탄사/웃음 효과음이 겹치지 않도록 자동 차단합니다.
- **브랜드 규칙**: 투자자는 항상 **"투자자"** 로 표기("샤크" 금지), 감탄사는 단독 자막(`solo: true`), 지폐 아이콘은 핵심 금액에 영상당 1회만 사용합니다.
- **즉시 복귀 스위치**: `AUTO_SFX_ENABLED=false`로 설정하면 기존 `sfx_level.py` / `sfx_opus.py` 로직으로 100% 동일하게 동작합니다.

## 4. 쇼츠 편집 · 자막 · 싱크 필수 표준 (모든 신규 주제 공통 적용)

새로운 주제의 영상을 제작하거나 새 채팅 세션에서 이어서 작업할 때 반드시 아래 기준을 기본값으로 적용합니다:

1. **초반 0~3초 강렬한 후킹**:
   - 평범한 도입부 대신 **초대박 매출액 공개, 창업자와의 거액 거래 성사 순간, 또는 가장 놀라운 제품 시연 장면**을 첫 3초 안에 배치합니다.
2. **가독성 최우선 1줄 자막 & 핵심 자막 확대 (`big` / `scale`)**:
   - 자막이 2줄로 겹쳐 읽기 힘들어지지 않도록 모든 자막은 **1줄 단독(`"solo": true`), 최대 3어절 이내**로 끊어 배치합니다.
   - 신기한 원리, 놀라운 반전, 거액 제안·매출 등 **대박 포인트 자막**은 `"big": true` 및 `"scale": 1.22 ~ 1.30`을 부여해 일반 자막(`74pt`)보다 크게 강조하고 탄력 팝업 효과를 적용합니다.
3. **화자 얼굴 노출 & 대본-화면-효과음 100% 싱크**:
   - 출연자나 투자자가 말하는 클립 구간에는 반드시 **말하는 사람의 얼굴(입모양·표정)** 이 화면에 명확히 보이도록 크롭/샷을 잡습니다.
   - 내레이션 구간의 화면(`shots`)은 해당 순간의 대본 설명(예: 찬물 입수, 무게 테스트, 세척 전후 비교 등)과 1:1로 일치해야 하며, 인접 구간과 같은 클립이 겹치지 않도록 구성합니다.
   - 효과음은 중복 파일 없이 컷 전환 또는 강조 자막 등장 프레임(`0.03s` 단위)에 피크를 맞추고, 렌더링 후 반드시 `python tools/gap_check.py`(오류 0건)와 `python tools/sub_onset_check.py`(오류 0건)를 통과해야 합니다.
4. **엔딩 무음 고정댓글 안내 컷 & 기본 납품 규칙**:
   - 마지막 대사가 끝난 뒤에는 TTS나 대사 없이 **별도의 전환된 컷 장면(`1.5~1.8초`)** 위에 `(자세한 내용은 고정댓글 참조)` 자막만 깔끔하게 띄워 마무리합니다.
   - 내레이션 TTS는 항상 **CapCut `'활기찬 바리톤'` (`vibrant_baritone`, `1.1x`)** 을 사용하고, 기존 버전(`v1`, `v2`, ...)은 덮어쓰지 않고 새 버전(`vN`)으로 저장한 뒤 `tools/send_mail.py`로 **네이버 내게쓰기** 발송까지 수행합니다.
5. **GitHub 원격 저장소 상시 푸시 (`origin/main`)**:
   - 코드, 설정, 편집 설계도(`vN_edl.json`) 등 작업이 완료되면 항상 `https://github.com/tmd3952wls/60SEC_YOUTUBE_AUTO_SHORT.git` (`origin`, `main` 브랜치)에 커밋하고 푸시(`git push origin main`)합니다. (`.env` 등 민감 정보는 절대 커밋하지 않습니다.)
