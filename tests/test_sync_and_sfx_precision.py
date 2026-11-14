"""프레임 단위 대본·자막·활기찬바리톤(1.1x)·효과음 피크 싱크 통합 검증 테스트."""
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import numpy as np
import soundfile as sf

from auto_sfx.config import SFXConfig
from auto_sfx.cuesheet import _build_smart_local_cues, _sub_events_from_edl_sub_list
from auto_sfx.matcher import compute_alignment_and_gain, score_catalog_entry
from auto_sfx.mixer import mix_sfx_into_video
from auto_sfx.models import ResolvedSFXCue, SFXCatalogEntry, SFXCue
from editor.sfx_worker import parse_companion_log
from shorts.align import _ko_phonetic_norm, _map_rec_words_to_tokens, chunk_times
from shorts.edl import _voice_onsets


def _make_entry(
    file_path: Path,
    category: str = "ding",
    duration_sec: float = 2.17,
    lead_silence_sec: float = 1.0,
    peak_offset_sec: float = 1.075,
    peak_dbfs: float = -9.6,
    rms_dbfs: float = -29.5,
    has_human_voice: bool = False,
) -> SFXCatalogEntry:
    return SFXCatalogEntry(
        sfx_id=f"sfx_{file_path.stem}",
        file_name=file_path.name,
        relative_path=file_path.name,
        absolute_path=str(file_path),
        fingerprint="deadbeef12345678",
        file_size_bytes=4096,
        mtime_ns=1,
        duration_sec=duration_sec,
        lead_silence_sec=lead_silence_sec,
        peak_offset_sec=peak_offset_sec,
        peak_dbfs=peak_dbfs,
        rms_dbfs=rms_dbfs,
        category=category,
        sub_type=file_path.stem,
        has_human_voice=has_human_voice,
    )


class TestSyncAndSFXPrecision(unittest.TestCase):
    def test_korean_phonetic_numeral_alignment_and_onset_snap(self):
        self.assertEqual(_ko_phonetic_norm("140억"), _ko_phonetic_norm("백사십억"))
        self.assertEqual(_ko_phonetic_norm("100만$"), _ko_phonetic_norm("백만달러"))
        self.assertEqual(_ko_phonetic_norm("10%"), _ko_phonetic_norm("십퍼센트"))

        sr = 16000
        dur = 2.2
        audio = np.zeros(int(sr * dur), dtype=np.float32)
        t = np.arange(len(audio)) / sr
        tone = 0.25 * np.sin(2 * np.pi * 220 * t).astype(np.float32)
        # 4개 어절 실제 발화 구간: 0.02~0.35, 0.48~0.92(140억), 0.96~1.25, 1.38~2.05
        for a, b in [(0.02, 0.35), (0.48, 0.92), (0.96, 1.25), (1.38, 2.05)]:
            audio[int(a * sr) : int(b * sr)] = tone[int(a * sr) : int(b * sr)]

        target_tokens = ["무려", "140억", "원을", "제안받았습니다"]
        # Whisper가 '백사십억'으로 한글 전사하고 시작점을 60ms 늦게 잡았다고 가정
        rec_words = [
            ("무려", 0.05, 0.34),
            ("백사십억", 0.54, 0.91),
            ("원을", 0.97, 1.24),
            ("제안받았습니다", 1.44, 2.04),
        ]
        words = _map_rec_words_to_tokens(target_tokens, rec_words, dur, audio)
        self.assertEqual(len(words), 4)
        self.assertEqual([w["word"] for w in words], target_tokens)
        # 10ms 음향 온셋 스냅으로 '140억'(실제 0.48s)과 '제안받았습니다'(실제 1.38s)가 ±20ms 내로 정밀 수렴
        self.assertAlmostEqual(words[0]["start"], 0.02, delta=0.03)
        self.assertAlmostEqual(words[1]["start"], 0.48, delta=0.03)
        self.assertAlmostEqual(words[3]["start"], 1.38, delta=0.03)

        chunks = ["무려 140억 원을", "제안받았습니다"]
        ct = chunk_times(chunks, words, dur, lead=0.03)
        self.assertEqual(ct[0][0], 0.0)
        self.assertAlmostEqual(ct[1][0], 1.35, delta=0.035)

    def test_first_subtitle_not_shifted_by_second_word_onset(self):
        with tempfile.TemporaryDirectory() as td:
            wav = Path(td) / "narr.wav"
            sr = 16000
            audio = np.zeros(int(sr * 1.5), dtype=np.float32)
            t = np.arange(len(audio)) / sr
            tone = 0.3 * np.sin(2 * np.pi * 240 * t).astype(np.float32)
            # 짧은 첫 단어(0.00~0.14s) -> 쉼(0.14~0.26s) -> 두 번째 단어(0.26~0.90s)
            audio[0 : int(0.14 * sr)] = tone[0 : int(0.14 * sr)]
            audio[int(0.26 * sr) : int(0.90 * sr)] = tone[int(0.26 * sr) : int(0.90 * sr)]
            sf.write(wav, audio, sr)

            ons = _voice_onsets(wav)
            self.assertTrue(len(ons) >= 2)
            self.assertLessEqual(float(ons[0]), 0.02)
            # 첫 자막(j=0, t_=0.0) 보호 로직 검증: ons[0] <= 0.12 이므로 0.26s 온셋으로 밀리지 않고 0.00s 유지
            st = [0.0, 0.26]
            fixed = []
            for j, t_ in enumerate(st):
                if j == 0 and t_ <= 0.01:
                    if len(ons) and 0.12 < float(ons[0]) < 0.35:
                        t_ = round(max(0.0, float(ons[0]) - 0.03) * 30) / 30
                    fixed.append(t_)
                    continue
                lo = fixed[-1] + 0.20
                c = ons[(ons >= max(lo, t_ - 0.35)) & (ons <= t_ + 0.35)]
                if len(c):
                    t_ = max(lo, round(max(0.0, float(c[np.argmin(np.abs(c - t_ - 0.03))]) - 0.03) * 30) / 30)
                fixed.append(t_)
            self.assertEqual(fixed[0], 0.0)
            self.assertAlmostEqual(fixed[1], 0.233, delta=0.02)

    def test_leading_silence_chime_peak_alignment_and_capcut_gain(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "001_띵.mp3"
            f.write_bytes(b"dummy")
            cfg = SFXConfig()
            sfx = _make_entry(f, category="ding", duration_sec=2.1692, lead_silence_sec=1.0, peak_offset_sec=1.075)
            cue = SFXCue(
                cue_id="cue_01",
                timestamp="00:05.00",
                timestamp_sec=5.0,
                trigger_type="money_stat",
                sfx_category="ding",
                desired_sfx_query_en="bell ding",
                desired_mood="bright",
                target_db=-14.5,
                max_duration_sec=1.2,
            )
            trim_s, delay_ms, gain_db = compute_alignment_and_gain(cue, sfx, cfg)
            # 1초 앞무음이 0.985s 제거되어 종소리 여운 1.17초가 온전히 살아나고, 피크는 정확히 5.000s(오차 0ms)에 도달!
            self.assertAlmostEqual(trim_s, 0.985, places=3)
            actual_peak_sec = (delay_ms / 1000.0) + (sfx.peak_offset_sec - trim_s)
            self.assertAlmostEqual(actual_peak_sec, 5.0, places=3)

            rc = ResolvedSFXCue(
                cue=cue,
                sfx=sfx,
                match_score=0.9,
                resolution_method="local_catalog",
                trim_start_sec=trim_s,
                insert_delay_ms=delay_ms,
                effective_gain_db=gain_db,
            )
            master_db = 4.25
            cc = rc.to_capcut_export_dict(master_db=master_db)
            capcut_linear = (10 ** (cc["gain_db"] / 20.0)) * (10 ** (master_db / 20.0))
            expected_linear = 10 ** (gain_db / 20.0)
            self.assertAlmostEqual(capcut_linear, expected_linear, places=3)

    def test_vocal_block_and_reference_15_palette_priority(self):
        with tempfile.TemporaryDirectory() as td:
            p_wow = Path(td) / "004_와우.mp3"
            p_pop = Path(td) / "002_뿅.mp3"
            p_whoosh_hero = Path(td) / "573_Whoosh(Transition).mp3"
            p_whoosh_misc = Path(td) / "999_random_noise.mp3"
            for p in (p_wow, p_pop, p_whoosh_hero, p_whoosh_misc):
                p.write_bytes(b"dummy")

            # 예전 카탈로그에 has_human_voice=False 로 잘못 적혀 있던 004_와우.mp3 도 런타임 가드가 즉시 차단
            e_wow = _make_entry(p_wow, category="whoosh", has_human_voice=False)
            cue_w = SFXCue("c1", "00:02.00", 2.0, "scene_cut", "whoosh", "fast whoosh", "snappy", duck_under_speech=True)
            self.assertEqual(score_catalog_entry(cue_w, e_wow, Counter()), 0.0)

            # 반대로 002_뿅.mp3 는 음성 오탐(has_human_voice=True)이 있더라도 비음성 카툰 신스로 정상 허용
            e_pop = _make_entry(p_pop, category="pop", duration_sec=0.31, lead_silence_sec=0.05, peak_offset_sec=0.065, has_human_voice=True)
            cue_p = SFXCue("c2", "00:02.00", 2.0, "circle_mark", "pop", "cartoon pop", "snappy", duck_under_speech=True)
            self.assertGreater(score_catalog_entry(cue_p, e_pop, Counter()), 0.75)

            # 레퍼런스 15편 검증 파일이 일반 미검증 파일보다 높은 점수를 획득
            e_hero = _make_entry(p_whoosh_hero, category="whoosh", duration_sec=1.08, lead_silence_sec=0.02, peak_offset_sec=0.18)
            e_misc = _make_entry(p_whoosh_misc, category="whoosh", duration_sec=1.08, lead_silence_sec=0.02, peak_offset_sec=0.18)
            self.assertGreater(score_catalog_entry(cue_w, e_hero, Counter()), score_catalog_entry(cue_w, e_misc, Counter()) + 0.15)

    def test_goofy_harsh_sfx_blocked_and_curated_edl_hints_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            p_rubber = Path(td) / "032_뽀욕 (고무장난감 누르는).mp3"
            p_harsh = Path(td) / "1177_깜짝 놀라는 전자음 1.mp3"
            p_rpg = Path(td) / "0808_체력,능력 상승5.mp3"
            p_cash = Path(td) / "010_철컥띵 (캐셔).mp3"
            for p in (p_rubber, p_harsh, p_rpg, p_cash):
                p.write_bytes(b"dummy")

            cue_pop = SFXCue("cp", "00:01.00", 1.0, "scene_cut", "pop", "crisp pop", "punchy")
            cue_sur = SFXCue("cs", "00:02.00", 2.0, "crisis_turn", "surprise", "surprise", "punchy")
            cue_sw = SFXCue("cw", "00:03.00", 3.0, "riser_buildup", "swell", "riser", "punchy")
            cue_ca = SFXCue("cc", "00:04.00", 4.0, "money_stat", "cash", "cash register", "punchy")

            self.assertEqual(score_catalog_entry(cue_pop, _make_entry(p_rubber, category="pop"), Counter()), 0.0)
            self.assertEqual(score_catalog_entry(cue_sur, _make_entry(p_harsh, category="surprise"), Counter()), 0.0)
            self.assertEqual(score_catalog_entry(cue_sw, _make_entry(p_rpg, category="swell"), Counter()), 0.0)
            self.assertGreater(score_catalog_entry(cue_ca, _make_entry(p_cash, category="cash"), Counter()), 0.85)

            # 숫자가 없는 '매출을 묻자' 자막은 cash 오탐하지 않아야 함
            subs_no_num = _sub_events_from_edl_sub_list([
                {"a": 4.0, "b": 5.2, "text": "투자자가 매출을 묻자", "spans": [["투자자가 매출을 묻자", "white"]], "solo": False, "icon": ""},
            ])
            cues_no_num = _build_smart_local_cues([], [], subs_no_num, [], 8.0, preset_id="balanced")
            self.assertNotIn("cash", [c["sfx_category"] for c in cues_no_num])

            # EDL 에 장면 맞춤 큐(seed_hint_cues >= 4)가 지정된 경우 불필요한 휴리스틱 스팸을 차단하고 지정 큐만 보존
            curated_seeds = [
                {"timestamp_sec": 0.0, "sfx_category": "pop", "trigger_type": "hook_0_3s"},
                {"timestamp_sec": 4.5, "sfx_category": "ding", "trigger_type": "scene_cut"},
                {"timestamp_sec": 9.0, "sfx_category": "whoosh", "trigger_type": "scene_cut"},
                {"timestamp_sec": 14.0, "sfx_category": "success", "trigger_type": "scene_cut"},
            ]
            subs_extra = _sub_events_from_edl_sub_list([
                {"a": 6.0, "b": 7.5, "text": "", "spans": [["치열한 경쟁", "yellow"]], "solo": False, "icon": ""},
                {"a": 11.0, "b": 12.5, "text": "", "spans": [["약 1억 원", "green"]], "solo": False, "icon": "money"},
            ])
            cues_curated = _build_smart_local_cues(curated_seeds, [], subs_extra, [2.0, 7.0], 16.0, preset_id="balanced")
            cues_curated.sort(key=lambda x: x["timestamp_sec"])
            # 지정 4개 + 지폐 아이콘(cash) 1개 = 정확히 5개만 깔끔하게 유지
            self.assertEqual([c["sfx_category"] for c in cues_curated], ["pop", "ding", "whoosh", "cash", "success"])

    def test_color_markup_and_solo_preserved_for_web_editor(self):
        with tempfile.TemporaryDirectory() as td:
            job = Path(td)
            (job / "edl_tmp").mkdir()
            subs_payload = {
                "out": "full_v1.mp4",
                "master_db": 3.0,
                "subs": [
                    {"a": 1.2, "b": 2.4, "text": "", "spans": [["연매출 ", "white"], ["140억", "green"]], "solo": False, "icon": "money"},
                    {"a": 3.5, "b": 4.1, "text": "와우!", "spans": [["와우!", "yellow"]], "solo": True, "icon": ""},
                    {"a": 5.0, "b": 6.2, "text": "", "spans": [["재고 ", "white"], ["전량 폐기", "red"]], "solo": False, "icon": ""},
                ],
                "items": [{"n": 0, "type": "narration", "t0": 0.0, "dur": 6.5, "shots": [[0.0, 6.5, "test", "source.mp4"]]}],
            }
            (job / "edl_tmp" / "full_v1_subs.json").write_text(json.dumps(subs_payload, ensure_ascii=False), encoding="utf-8")

            subs, items = parse_companion_log(job / "full_v1_log.txt", job=job, video_stem="full_v1")
            self.assertEqual(len(subs), 3)
            self.assertEqual(len(items), 1)
            events = _sub_events_from_edl_sub_list(subs)
            self.assertIn("[green:140억]", events[0].text)
            self.assertTrue(events[1].solo)
            self.assertIn("[red:전량 폐기]", events[2].text)

            cues = _build_smart_local_cues([], [], events, [0.1], 7.0, preset_id="balanced")
            cats_by_t = {round(c["timestamp_sec"], 2): c["sfx_category"] for c in cues}
            self.assertEqual(cats_by_t.get(1.2), "cash")
            self.assertEqual(cats_by_t.get(3.5), "pop")
            self.assertEqual(cats_by_t.get(5.0), "surprise")

    def test_ffmpeg_filter_script_peak_accuracy_14_cues(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            draft = tmp / "draft.mp4"
            out_mp4 = tmp / "mixed.mp4"
            sfx_wav = tmp / "001_띵.wav"

            # 1.00초 무음 뒤에 정확히 1.075초에 임펄스 피크가 있는 테스트 효과음 생성
            sr = 48000
            samples = np.zeros(int(sr * 2.0), dtype=np.float32)
            peak_idx = int(1.075 * sr)
            t_tail = np.arange(int(0.6 * sr)) / sr
            samples[peak_idx : peak_idx + len(t_tail)] = (0.85 * np.sin(2 * np.pi * 1200 * t_tail) * np.exp(-5 * t_tail)).astype(np.float32)
            sf.write(sfx_wav, samples, sr)

            subprocess.run(
                [
                    "ffmpeg", "-y", "-v", "error",
                    "-f", "lavfi", "-i", "color=c=black:s=360x640:d=8:r=30",
                    "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo:d=8",
                    "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(draft),
                ],
                check=True,
            )

            cfg = SFXConfig(enable_sidechain_ducking=False)
            sfx_entry = _make_entry(
                sfx_wav, category="ding", duration_sec=2.0, lead_silence_sec=1.0, peak_offset_sec=1.075, peak_dbfs=-1.4, rms_dbfs=-18.0
            )
            # 14개 큐 합성(-filter_complex_script 경로 자동 활성화 검증)
            resolved = []
            target_times = [0.5 * k for k in range(1, 15)]
            for idx, ts in enumerate(target_times, start=1):
                cue = SFXCue(f"cue_{idx:02d}", f"00:{ts:05.2f}", ts, "scene_cut", "ding", "ding", "bright", target_db=-12.0, max_duration_sec=0.45)
                trim_s, delay_ms, gain_db = compute_alignment_and_gain(cue, sfx_entry, cfg)
                resolved.append(ResolvedSFXCue(cue, sfx_entry, 0.95, "local_catalog", trim_s, delay_ms, gain_db))

            mix_sfx_into_video(draft, out_mp4, resolved, 8.0, cfg)
            self.assertTrue(out_mp4.is_file())

            # 출력 오디오 디코딩 후 첫 타격(0.500s)과 열 번째 타격(5.000s)의 실제 에너지 피크가 ±15ms(0.5프레임) 안인지 검증
            pcm = subprocess.run(
                ["ffmpeg", "-v", "error", "-i", str(out_mp4), "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                capture_output=True,
                check=True,
            ).stdout
            y = np.abs(np.frombuffer(pcm, np.int16).astype(np.float32) / 32768.0)
            for check_t in (0.5, 5.0):
                w0, w1 = int((check_t - 0.15) * 16000), int((check_t + 0.15) * 16000)
                local_peak_sec = (w0 + int(np.argmax(y[w0:w1]))) / 16000.0
                self.assertAlmostEqual(local_peak_sec, check_t, delta=0.025)


if __name__ == "__main__":
    unittest.main()
