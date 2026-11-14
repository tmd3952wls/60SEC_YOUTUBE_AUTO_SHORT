# AGENTS.md — Antigravity (`agy`) & 웹 에디터 로컬 실행 지침서

이 문서는 로컬 Windows PC에서 과금 걱정 없이 2,869개 로컬 효과음을 색인하고, **웹 에디터(`run_editor.bat`)** 및 [Google Antigravity CLI (`agy`)](https://antigravity.google/docs/cli/best-practices/)로 60초 쇼츠 효과음 연출·검수·CapCut 내보내기를 수행하는 표준 플레이북입니다.

## 1. 최초 1회 환경 구성 (0원 무과금 기준 · Windows PowerShell)

```powershell
# 1) 환경변수 파일 복사 (API 키를 하나도 안 넣어도 local-free 모드로 즉시 작동!)
copy .env.example .env

# 2) 내 로컬 효과음 2,869개 무료 파형·파일명 고속 색인 (API 호출 0회 · 완전 무료)
python -m auto_sfx.director index --offline

# (선택) Google GenAI SDK 설치 — 나중에 AI Studio 무료 티어 키를 쓸 때만 설치해도 됩니다
pip install -r requirements-sfx.txt
```

## 2. 웹 에디터에서 화면 보며 효과음 넣기 (가장 추천하는 방법)

```powershell
run_editor.bat
# 또는: python editor/server.py
```

1. 브라우저가 열리면 상단에서 **작업**과 **영상**을 고릅니다.
2. 왼쪽 **`AI 효과음`** 탭을 누르고 연출 방식(`무료 로컬 자동 (0원)` / `Antigravity CLI 연동 (0원)` / `Gemini 영상 시청`)을 고른 뒤 **`큐시트 자동 짜기`** 를 클릭합니다.
3. 타임스탬프 버튼을 눌러 장면을 확인하고, 바꾸고 싶은 소리는 드롭다운이나 왼쪽 **`효과음 폴더`** 탭(2,869개 실시간 검색·미리듣기)에서 골라 바꿉니다.
4. **`소리만 다시 입히기 (2초 완성)`** 버튼을 누르면 영상을 다시 렌더링하지 않고(`-c:v copy`) 2초 만에 `full_v17_sfx1.mp4` 새 파일로 완성되어 바로 재생됩니다!
5. 우측 상단 **톱니바퀴(설정)** 에서 언제든 자동 효과음 디렉터 ON/OFF, 기본 엔진 변경, 2,869개 무료 재색인을 실행할 수 있습니다.

## 3. 터미널 / `agy` CLI 실행 워크플로

```powershell
# A. EDL 전체 렌더링 (자막 번인 + 자동 효과음 + BGM 한 번에)
python editor/render_worker.py --job coconut --edl v17_edl.json --out full_v18.mp4 --preset 해외쇼쇼

# B. 완성된 결과를 CapCut 트랙별 프로젝트로 내보내기 (리믹스한 효과음도 트랙별로 분리됨)
python -m shorts.capcut --job coconut --edl v17_edl.json

# C. 초안 영상에 터미널에서 0원 오프라인 모드로 효과음만 2초 합성
python -m auto_sfx.director run --video jobs/coconut/full_v17.mp4 --backend local-free --offline-catalog --output jobs/coconut/full_v17_sfx1.mp4

# D. agy CLI 로 큐시트 싱크 검수 시키기
agy -p "jobs/coconut/full_v17_sfx1_sfx_cuesheet.json 과 jobs/coconut/full_v17_sfx1_log.txt 를 비교해 초반 3초 훅과 매출 자막 타격 싱크를 검수해 줘."
```

## 4. 코드 수정 후 필수 검증 루프

```powershell
python -m unittest discover -s tests -v
```
