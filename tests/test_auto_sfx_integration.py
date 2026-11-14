"""Integration tests verifying Auto SFX Director, Presets, ★ Favorites, CapCut Vibrant Baritone, One-Click CapCut Export & New Job Creation."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from auto_sfx.cataloger import SFXCatalogManager
from auto_sfx.config import SFXConfig, is_auto_sfx_enabled
from auto_sfx.director import apply_auto_sfx_if_enabled, run_edl_auto_sfx_stage


def _run_ffmpeg(args: list[str]) -> None:
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], check=True, timeout=30)


class IntegratedAutoSFXTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.sfx_dir = self.root / "효과음2869개"
        (self.sfx_dir / "전환").mkdir(parents=True, exist_ok=True)
        (self.sfx_dir / "강조").mkdir(parents=True, exist_ok=True)
        self.catalog_path = self.root / "assets" / "sfx_catalog.json"
        self.fav_path = self.root / "assets" / "sfx_favorites.json"
        self.cuesheet_dir = self.root / "jobs" / "_cuesheets"
        self.job_dir = self.root / "jobs" / "sample_job"
        self.job_dir.mkdir(parents=True, exist_ok=True)

        _run_ffmpeg([
            "-f", "lavfi", "-i", "aevalsrc='if(between(t,0.20,0.35),0.9*sin(2*PI*620*t),0.01*sin(2*PI*180*t))':s=16000:d=0.55",
            str(self.sfx_dir / "전환" / "001_fast_clean_whoosh_swipe.wav"),
        ])
        _run_ffmpeg([
            "-f", "lavfi", "-i", "aevalsrc='if(between(t,0.18,0.32),0.88*sin(2*PI*540*t),0.01*sin(2*PI*150*t))':s=16000:d=0.60",
            str(self.sfx_dir / "전환" / "999_내최애_whoosh.wav"),
        ])
        _run_ffmpeg([
            "-f", "lavfi", "-i", "aevalsrc='if(between(t,0.02,0.12),0.88*sin(2*PI*1400*t),0)':s=16000:d=0.45",
            str(self.sfx_dir / "강조" / "292_Cash_Register_철컥띵.wav"),
        ])
        _run_ffmpeg([
            "-f", "lavfi", "-i", "aevalsrc='if(between(t,0.08,0.25),0.95*sin(2*PI*95*t),0)':s=16000:d=0.80",
            str(self.sfx_dir / "강조" / "007_쿵_impact.wav"),
        ])
        _run_ffmpeg([
            "-f", "lavfi", "-i", "aevalsrc='0.7*(t/0.5)*sin(2*PI*420*t)':s=16000:d=0.55",
            str(self.sfx_dir / "전환" / "099_riser_swell.wav"),
        ])
        _run_ffmpeg([
            "-f", "lavfi", "-i", "sine=frequency=500:sample_rate=16000:duration=0.5",
            str(self.sfx_dir / "강조" / "246_와우_wow.wav"),
        ])

        self.draft_mp4 = self.job_dir / "full_v1.mp4"
        _run_ffmpeg([
            "-f", "lavfi", "-i", "testsrc2=s=360x640:r=30:d=3.0",
            "-f", "lavfi", "-i", "color=c=yellow:s=360x640:r=30:d=3.0",
            "-f", "lavfi", "-i", "color=c=blue:s=360x640:r=30:d=3.0",
            "-f", "lavfi", "-i", "color=c=red:s=360x640:r=30:d=3.0",
            "-f", "lavfi", "-i",
            "aevalsrc='if(between(t,0.20,1.40),0.6*sin(2*PI*220*t), if(between(t,4.50,6.00),0.65*sin(2*PI*300*t),0))':s=48000:d=12.0",
            "-filter_complex", "[0:v][1:v][2:v][3:v]concat=n=4:v=1:a=0[v]",
            "-map", "[v]", "-map", "4:a",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            str(self.draft_mp4),
        ])

    def tearDown(self) -> None:
        for k in [
            "AUTO_SFX_ENABLED",
            "LOCAL_SFX_DIR",
            "SFX_CATALOG_PATH",
            "SFX_FAVORITES_PATH",
            "SFX_CUESHEET_DIR",
            "SFX_DIRECTOR_BACKEND",
            "SFX_STYLE_PRESET",
            "LOCALAPPDATA",
        ]:
            os.environ.pop(k, None)
        self.tmp.cleanup()

    def test_recursive_incremental_catalog_and_vocal_filter(self) -> None:
        cfg = SFXConfig(
            auto_sfx_enabled=True,
            local_sfx_dir=self.sfx_dir,
            fallback_repo_sfx_dirs=[],
            catalog_path=self.catalog_path,
            favorites_path=self.fav_path,
            cuesheet_dir=self.cuesheet_dir,
        )
        mgr = SFXCatalogManager(cfg)
        s1 = mgr.sync_incremental()
        self.assertEqual(s1["added_or_updated"], 6)
        wow_entry = mgr.entries_by_rel_path["강조/246_와우_wow.wav"]
        self.assertTrue(wow_entry.has_human_voice)

        s2 = SFXCatalogManager(cfg).sync_incremental()
        self.assertEqual(s2["added_or_updated"], 0)
        self.assertEqual(s2["skipped_cached"], 6)

    def test_edl_stage_hook_and_capcut_export_schema(self) -> None:
        os.environ["AUTO_SFX_ENABLED"] = "true"
        os.environ["SFX_DIRECTOR_BACKEND"] = "local-free"
        os.environ["LOCAL_SFX_DIR"] = str(self.sfx_dir)
        os.environ["SFX_CATALOG_PATH"] = str(self.catalog_path)
        os.environ["SFX_FAVORITES_PATH"] = str(self.fav_path)
        os.environ["SFX_CUESHEET_DIR"] = str(self.cuesheet_dir)

        sub_list = [
            {"a": 0.15, "b": 2.10, "text": "[yellow:역대급] 제품 등장", "spans": [("역대급", "yellow"), (" 제품 등장", "white")]},
            {"a": 4.45, "b": 6.10, "text": "연 매출 [green:140억] 달성!", "spans": [("연 매출 ", "white"), ("140억", "green"), (" 달성!", "white")]},
        ]
        exp_items = [
            {"n": 0, "type": "narration", "t0": 0.0, "dur": 3.0, "shots": [[0.0, 3.0, "훅", "source.mp4"]]},
            {"n": 1, "type": "narration", "t0": 3.0, "dur": 4.0, "shots": [[3.0, 6.0, "매출", "source.mp4"], [6.0, 7.0, "전환", "source.mp4"]]},
        ]
        exp_sfx, _avg_db, log_lines = run_edl_auto_sfx_stage(
            job=self.job_dir,
            video=self.draft_mp4,
            total=12.0,
            edl_hints=[(0.15, "impact"), (4.45, "cash"), (6.00, "whoosh")],
            sub_list=sub_list,
            exp_items=exp_items,
            master_db=-16.0,
            repo_cfg={"render": {"sfx_engine": "auto"}},
        )
        self.assertTrue(self.draft_mp4.is_file())
        self.assertGreaterEqual(len(exp_sfx), 2)
        self.assertTrue(len(log_lines) >= 1)

    def test_feature_flag_off_preserves_original_render_video(self) -> None:
        os.environ["AUTO_SFX_ENABLED"] = "false"
        self.assertFalse(is_auto_sfx_enabled({"auto_sfx": {"enabled": False}}))
        before = self.draft_mp4.read_bytes()
        apply_auto_sfx_if_enabled(self.draft_mp4, repo_cfg={"auto_sfx": {"enabled": False}})
        self.assertEqual(before, self.draft_mp4.read_bytes())

    def test_plan_to_edl_converter_and_brand_rules(self) -> None:
        from editor.new_job_worker import plan_to_edl, split_narration_subs
        from editor.server import suggest_job_name

        narr = "출시 3년 만에 [yellow:140억 원]을 벌어들인 신기한 빨대가 있는데"
        subs = split_narration_subs(narr, max_chars=12)
        joined_plain = "".join(s["text"].replace("[yellow:", "").replace("]", "") for s in subs).replace(" ", "")
        orig_plain = narr.replace("[yellow:", "").replace("]", "").replace(" ", "")
        self.assertEqual(joined_plain, orig_plain)
        self.assertTrue(any("[yellow:140억 원]" in s["text"] for s in subs))

        transcript = [
            {"id": 0, "start": 1.0, "end": 4.0, "text": "Look at how fast this opens a coconut."},
            {"id": 1, "start": 4.2, "end": 5.2, "text": "Wow!"},
            {"id": 2, "start": 5.3, "end": 8.0, "text": "Our sales reached two million dollars."},
        ]
        words_map = {
            "0": [{"w": "Look", "s": 1.0, "e": 2.0}, {"w": "coconut.", "s": 2.0, "e": 4.0}],
            "1": [{"w": "Wow!", "s": 4.2, "e": 5.2}],
            "2": [{"w": "Our", "s": 5.3, "e": 6.5}, {"w": "sales", "s": 6.5, "e": 8.0}],
        }
        plan = {
            "title_lines": ["망치 없이 코코넛을", "빨대로 뚫는다고?!"],
            "segments": [
                {"type": "narration", "text": "샤크들도 깜짝 놀란 코코넛 빨대인데", "broll_id": 0, "sfx": "boom"},
                {"type": "clip", "from_id": 1, "to_id": 2, "subs": ["[cyan:와우!]", "매출이 [green:200만 달러]예요"], "sfx": "cash"},
            ],
        }
        edl = plan_to_edl(plan, transcript, words_map, {"subtitle": {"max_chars": 12}}, title_hint="코코넛을 이제는 / 빨대로 뚫는다고?!")
        self.assertEqual(edl["title_lines"][0]["text"], "코코넛을 이제는")
        self.assertEqual(edl["title_lines"][1]["text"], "빨대로 뚫는다고?!")
        self.assertNotIn("샤크", edl["items"][0]["text"])
        self.assertIn("투자자", edl["items"][0]["text"])
        self.assertEqual(edl["items"][0]["sfx"], "impact")
        clip_it = edl["items"][1]
        self.assertEqual(clip_it["ids"], [1, 2])
        self.assertTrue(clip_it["subs"][0].get("solo"))
        self.assertEqual(clip_it["subs"][1]["at_word"], 1)

        self.assertEqual(suggest_job_name("", "", "https://www.youtube.com/shorts/2jJoIbdciDY"), "yt_2jJoIbdciDY")
        self.assertEqual(suggest_job_name("", "망치 없이 코코넛 / 빨대", "https://youtu.be/abc123XYZ"), "망치_없이_코코넛")

    def test_web_editor_baritone_favorites_capcut_and_new_job_api(self) -> None:
        import editor.server as esrv

        os.environ["LOCALAPPDATA"] = str(self.root / "AppData" / "Local")
        test_job_name = "_unit_sfx_web_test"
        created_job_name = "unit_new_job_test"
        real_job_dir = esrv.JOBS / test_job_name
        created_job_dir = esrv.JOBS / created_job_name
        orig_env = esrv.ENV.read_text(encoding="utf-8") if esrv.ENV.exists() else None
        orig_cfg = esrv.CONFIG.read_text(encoding="utf-8")
        orig_cat = (esrv.ASSETS / "sfx_catalog.json").read_text(encoding="utf-8") if (esrv.ASSETS / "sfx_catalog.json").exists() else None
        orig_fav = esrv.FAVORITES.read_text(encoding="utf-8") if esrv.FAVORITES.exists() else None

        srv = ThreadingHTTPServer(("127.0.0.1", 0), esrv.H)
        port = srv.server_address[1]
        th = threading.Thread(target=srv.serve_forever, daemon=True)
        th.start()
        base_url = f"http://127.0.0.1:{port}"

        def http_json(path: str, payload: dict | None = None) -> dict:
            if payload is None:
                with urllib.request.urlopen(base_url + path, timeout=15) as r:
                    return json.loads(r.read().decode("utf-8"))
            req = urllib.request.Request(
                base_url + path,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read().decode("utf-8"))

        try:
            if created_job_dir.exists():
                shutil.rmtree(created_job_dir)
            real_job_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.draft_mp4, real_job_dir / "source.mp4")
            shutil.copy2(self.draft_mp4, real_job_dir / "full_v1.mp4")
            (real_job_dir / "edl_tmp").mkdir(exist_ok=True)
            shutil.copy2(self.draft_mp4, real_job_dir / "edl_tmp" / "body.mp4")
            _run_ffmpeg(["-i", str(self.draft_mp4), "-vn", "-c:a", "aac", str(real_job_dir / "edl_tmp" / "full_v1_voice.m4a")])

            edl_payload = {
                "title_lines": [{"text": "테스트 상단", "color": "yellow"}, {"text": "두번째 줄", "color": "white"}],
                "items": [
                    {"type": "narration", "text": "첫 번째 테스트 문장인데", "subs": [{"text": "첫 번째 테스트 문장인데"}], "shots": [{"src": 0.0, "crop": [180, 320, 640]}], "sfx": "impact"},
                    {"type": "narration", "text": "연 매출 140억을 기록했고", "subs": [{"text": "연 매출 [green:140억]을 기록했고"}], "shots": [{"src": 3.0, "crop": [180, 320, 640]}], "sfx": "cash"},
                    {"type": "narration", "text": "결국 계약에 성공했다고 해", "subs": [{"text": "결국 계약에 성공했다고 해"}], "shots": [{"src": 6.0, "crop": [180, 320, 640]}], "sfx": "success"},
                ],
            }
            (real_job_dir / "v1_edl.json").write_text(json.dumps(edl_payload, ensure_ascii=False), encoding="utf-8")
            (real_job_dir / "full_v1_meta.json").write_text(
                json.dumps({"edl": "v1_edl.json", "items": None, "draft": False, "duration": 12.0}, ensure_ascii=False),
                encoding="utf-8",
            )
            (real_job_dir / "full_v1_log.txt").write_text(
                "\n".join([
                    "item0 [narration] 0.00~3.00s  단어: 첫@0.15",
                    "item1 [narration] 3.00~7.00s  단어: 매출@4.50",
                    "item2 [narration] 7.00~12.00s  단어: 성공@8.00",
                    "  [최종 자막] 0.15~2.20 (2.05s): 첫 번째 테스트 문장인데",
                    "  [최종 자막] 4.45~6.20 (1.75s): 연 매출 140억을 기록했고",
                    "  [최종 자막] 8.00~11.00 (3.00s): 결국 계약에 성공했다고 해",
                ]),
                encoding="utf-8",
            )
            fake_wav = self.sfx_dir / "전환" / "001_fast_clean_whoosh_swipe.wav"
            (real_job_dir / "edl_tmp" / "export.json").write_text(
                json.dumps(
                    {
                        "out": "full_v1.mp4",
                        "total": 12.0,
                        "top": 420,
                        "panel": [1080, 1050],
                        "master_db": 0.0,
                        "title_lines": edl_payload["title_lines"],
                        "bgm": None,
                        "items": [
                            {"n": 0, "type": "narration", "t0": 0.0, "dur": 3.0, "wav": str(fake_wav), "gain_db": 0.0, "shots": [[0.0, 3.0, "훅", "source.mp4"]]},
                            {"n": 1, "type": "narration", "t0": 3.0, "dur": 4.0, "wav": str(fake_wav), "gain_db": 0.0, "shots": [[3.0, 7.0, "매출", "source.mp4"]]},
                            {"n": 2, "type": "narration", "t0": 7.0, "dur": 5.0, "wav": str(fake_wav), "gain_db": 0.0, "shots": [[7.0, 12.0, "결말", "source.mp4"]]},
                        ],
                        "subs": [
                            {"a": 0.15, "b": 2.20, "spans": [["첫 번째 테스트 문장인데", "white"]], "item": 0, "text": "첫 번째 테스트 문장인데", "krw": "", "note": "", "solo": False, "icon": ""},
                        ],
                        "sfx": [],
                        "icon": None,
                        "circles": [],
                        "ass_head": [],
                        "sub_pos": [540, 960],
                        "sub_an": 5,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            # 1) Verify UI HTML serves + 새 작업 button, #newjob-modal, CapCut export & vibrant_baritone
            with urllib.request.urlopen(base_url + "/", timeout=10) as r:
                html_text = r.read().decode("utf-8")
            self.assertIn('id="btn-new-job"', html_text)
            self.assertIn('id="newjob-modal"', html_text)
            self.assertIn('id="btn-capcut"', html_text)
            self.assertIn("활기찬 바리톤", html_text)

            # 2) Verify POST /api/jobs/create creates source.mp4 + transcript_words.json + v1_edl.json end-to-end!
            created_job_dir.mkdir(parents=True, exist_ok=True)
            (created_job_dir / "transcript.json").write_text(
                json.dumps([
                    {"id": 0, "start": 0.2, "end": 2.8, "text": "This straw opens a fresh coconut in three seconds."},
                    {"id": 1, "start": 3.2, "end": 5.6, "text": "Wow, our sales hit one million dollars."},
                    {"id": 2, "start": 6.0, "end": 9.0, "text": "You got yourself a deal!"},
                ], ensure_ascii=False),
                encoding="utf-8",
            )
            nj_res = http_json("/api/jobs/create", {
                "name": created_job_name,
                "src": str(self.draft_mp4),
                "title_hint": "망치 없이 코코넛을 / 빨대로 뚫는다고?!",
                "context": "샤크탱크 코코넛 빨대 테스트",
                "script_mode": "starter",
                "start": 0,
                "end": 10,
            })
            self.assertTrue(nj_res["started"])
            self.assertEqual(nj_res["job"], created_job_name)
            for _ in range(60):
                t_info = http_json("/api/task")
                if not t_info["running"]:
                    break
                time.sleep(0.25)
            self.assertTrue(t_info["ok"], msg=f"New job log: {t_info.get('log')}")
            self.assertTrue((created_job_dir / "source.mp4").is_file())
            self.assertTrue((created_job_dir / "transcript_words.json").is_file())
            self.assertTrue((created_job_dir / "v1_edl.json").is_file())

            jobs_list = http_json("/api/jobs")
            self.assertTrue(any(j["name"] == created_job_name for j in jobs_list))
            created_edl = http_json(f"/api/edl?job={urllib.parse.quote(created_job_name)}&file=v1_edl.json")
            self.assertEqual(created_edl["title_lines"][0]["text"], "망치 없이 코코넛을")
            self.assertEqual(created_edl["title_lines"][1]["text"], "빨대로 뚫는다고?!")
            self.assertGreaterEqual(len(created_edl["items"]), 3)

            # 3) Verify CapCut vibrant_baritone 1.1x TTS status & CapCut voice make endpoint
            tts_st = http_json("/api/tts/status", {"job": test_job_name, "edl": edl_payload})
            self.assertEqual(tts_st["provider"], "capcut")
            self.assertEqual(tts_st["voice"], "vibrant_baritone")
            self.assertAlmostEqual(tts_st["speed"], 1.1)
            self.assertEqual(tts_st["total_narr"], 3)

            make_res = http_json("/api/tts/capcut/make", {"job": test_job_name, "edl_file": "v1_edl.json"})
            self.assertTrue(make_res["started"])
            for _ in range(40):
                t_info = http_json("/api/task")
                if not t_info["running"]:
                    break
                time.sleep(0.2)
            self.assertTrue(t_info["ok"], msg=f"TTS make log: {t_info.get('log')}")
            self.assertTrue((real_job_dir / "capcut_voice_vibrant_baritone.json").is_file())

            # 4) Index SFX, star ★ "999_내최애_whoosh", generate punchy cuesheet, apply 2s remix -> full_v1_sfx1.mp4
            http_json("/api/settings", {
                "sfx_dir": str(self.sfx_dir),
                "auto_sfx_enabled": True,
                "director_backend": "local-free",
                "style_preset": "punchy",
            })
            http_json("/api/sfx/reindex", {"mode": "free"})
            for _ in range(40):
                t_info = http_json("/api/task")
                if not t_info["running"]:
                    break
                time.sleep(0.2)
            self.assertTrue(t_info["ok"])

            http_json("/api/sfx/favorite", {"name": "999_내최애_whoosh"})
            gen_punchy = http_json("/api/cuesheet/generate", {
                "job": test_job_name,
                "video": "full_v1.mp4",
                "edl_file": "v1_edl.json",
                "backend": "local-free",
                "style_preset": "punchy",
            })
            cues_punchy = gen_punchy["cuesheet"]["cues"]
            if not any(c["sfx_category"] == "whoosh" and not c.get("pinned_name") for c in cues_punchy):
                cues_punchy[0]["sfx_category"] = "whoosh"
                cues_punchy[0]["pinned_name"] = ""

            http_json("/api/cuesheet/apply", {
                "job": test_job_name,
                "video": "full_v1.mp4",
                "edl_file": "v1_edl.json",
                "cuesheet": gen_punchy["cuesheet"],
            })
            for _ in range(50):
                t_info = http_json("/api/task")
                if not t_info["running"]:
                    break
                time.sleep(0.2)
            self.assertTrue(t_info["ok"], msg=f"Remix log: {t_info.get('log')}")

            # 5) One-click CapCut Export reflecting full_v1_sfx1.mp4 remixed SFX tracks!
            cc_exp = http_json("/api/capcut/export", {
                "job": test_job_name,
                "edl_file": "v1_edl.json",
                "video": "full_v1_sfx1.mp4",
                "preset": "해외쇼쇼",
                "name": "test_cc_sfx_proj",
            })
            self.assertTrue(cc_exp["started"])
            for _ in range(60):
                t_info = http_json("/api/task")
                if not t_info["running"]:
                    break
                time.sleep(0.2)
            self.assertTrue(t_info["ok"], msg=f"CapCut export log: {t_info.get('log')}")

            draft_dir = Path(os.environ["LOCALAPPDATA"]) / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft" / "test_cc_sfx_proj"
            self.assertTrue((draft_dir / "draft_content.json").is_file())
            draft_json = json.loads((draft_dir / "draft_content.json").read_text(encoding="utf-8"))
            audio_names = [a.get("path", "") or a.get("name", "") for a in draft_json["materials"].get("audios", [])]
            self.assertTrue(any("999_내최애_whoosh" in nm for nm in audio_names), msg=f"Audios: {audio_names}")
        finally:
            srv.shutdown()
            srv.server_close()
            for jd in (real_job_dir, created_job_dir):
                if jd.exists():
                    shutil.rmtree(jd)
            if orig_env is None:
                esrv.ENV.unlink(missing_ok=True)
            else:
                esrv.ENV.write_text(orig_env, encoding="utf-8")
            esrv.CONFIG.write_text(orig_cfg, encoding="utf-8")
            if orig_cat is None:
                (esrv.ASSETS / "sfx_catalog.json").unlink(missing_ok=True)
            else:
                (esrv.ASSETS / "sfx_catalog.json").write_text(orig_cat, encoding="utf-8")
            if orig_fav is None:
                esrv.FAVORITES.unlink(missing_ok=True)
            else:
                esrv.FAVORITES.write_text(orig_fav, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
