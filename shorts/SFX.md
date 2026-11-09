# 효과음 (기본: opus-sound-layer)

2026-11-08부터 렌더러(`shorts/edl.py`)는 효과음을 **실제 녹음 CC0 라이브러리**로 따로 섞습니다. 예전 효과음 폴더의 소리가 어색했기 때문입니다.
- 라이브러리는 `ext/opus-sound-layer`, 효과음 1,139개입니다.
- `full_v6` 판을 듣고 정한 방식입니다.

## 동작 순서
1. EDL의 `sfx` / `sfx2` / 원 `sfx`가 언제, 어떤 종류(whoosh, pop, ding…)를 낼지 정합니다. 이 부분은 예전과 같습니다.
2. 소리는 `shorts/sfx_opus.py`의 `FAMILY`에서 종류별로 차례대로 고릅니다. 한 영상 안에서는 같은 소리를 되도록 다시 쓰지 않습니다.
   - 소리 계열: 공기 휙, 천 스치는 소리, 물방울 팝, 나무 톡, 종
   - `impact`는 큰 한 방입니다. 직전에 잠깐 정적을 두고 짧게 차오르는 소리를 겹칩니다.
   - 특정 소리를 쓰려면 EDL에 라이브러리 id를 직접 적습니다(예: `"sfx": "whoosh/fs-30240-swoop1-flac-1"`).
     - 예전 고정 이름(`"pop/카툰 팝"`)을 적으면 같은 종류에서 고릅니다.
3. opus `mix.py`가 섞습니다.
   - 효과음은 소리의 정점이 정한 시점에 오도록 놓습니다.
   - 음량은 목소리를 기준으로 효과음마다 따로 정합니다.
   - 모든 효과음에 같은 공간 울림을 입히고, 전체를 -14 LUFS로 맞춥니다.
4. `qa.py`로 검사합니다. 안 들린다고 나온 효과음은 같은 종류의 다른 소리로 바꿔 최대 2번 다시 섞습니다. 결과는 `<영상>_log.txt`에 남습니다.

## 예전 방식으로 돌리기
- `config.json`의 `render`에 `"sfx_engine": "old"`를 넣으면 예전 효과음 폴더로 섞습니다.
- `ext/opus-sound-layer`나 `uv`가 없을 때도 자동으로 예전 방식을 씁니다. 이때 로그에 ⚠ 표시가 남습니다.

## 설치 (다른 PC)
```
pip install uv
git clone https://github.com/Bodila51/opus-sound-layer ext/opus-sound-layer
cd ext/opus-sound-layer && uv run scripts/sfx.py kit
```
- `sfx.py kit`에 적힌 Kenney 다운로드 주소는 낡아서, Kenney 묶음 7개를 받지 못하고 830개만 생깁니다.
- 나머지는 Kenney 페이지에서 받은 zip을 `audio/kit/_raw/kenney_<이름>.zip`에 넣고 `kit`을 다시 실행하면 됩니다.

## 출처
라이브러리 소리는 모두 CC0입니다. 출처 목록은 `ext/opus-sound-layer/audio/kit/CREDITS.md`에 있습니다.
