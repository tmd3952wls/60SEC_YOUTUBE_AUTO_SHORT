"""웹 에디터 전용 AI 효과음 작업기 (색인 · 프리셋 큐시트 생성 · 2초 고속 오디오 재합성).

server.py 의 start_task() 로 호출되어 진행 상황을 실시간 로그로 출력합니다.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

from auto_sfx.cataloger import SFXCatalogManager  # noqa: E402
from auto_sfx.config import SFXConfig, get_style_preset_spec, normalize_style_preset  # noqa: E402
from auto_sfx.cuesheet import generate_sfx_cuesheet  # noqa: E402
from auto_sfx.matcher import resolve_cuesheet  # noqa: E402
from auto_sfx.mixer import mix_sfx_into_video  # noqa: E402
from auto_sfx.models import SFXCuesheet  # noqa: E402
from shorts.common import JOBS, load_config  # noqa: E402


def parse_companion_log(log_path: Path, job: Path | None = None, video_stem: str = ""):
    """edl_tmp/<stem>_subs.json 또는 export.json(색상 마크업·solo 포함)을 최우선 복원하고, 없으면 <stem>_log.txt 에서 복원."""
    if job is not None and video_stem:
        cands = [job / "edl_tmp" / f"{video_stem}_subs.json"]
        meta_p = job / f"{video_stem}_meta.json"
        if meta_p.is_file():
            try:
                base_v = (json.loads(meta_p.read_text(encoding="utf-8")) or {}).get("sfx_base_video")
                if base_v:
                    cands.append(job / "edl_tmp" / f"{Path(base_v).stem}_subs.json")
            except Exception:
                pass
        for cp in cands:
            if cp.is_file():
                try:
                    doc = json.loads(cp.read_text(encoding="utf-8"))
                    if doc.get("subs") is not None:
                        return list(doc.get("subs") or []), list(doc.get("items") or [])
                except Exception:
                    pass
        exp_p = job / "edl_tmp" / "export.json"
        if exp_p.is_file():
            try:
                edoc = json.loads(exp_p.read_text(encoding="utf-8"))
                out_stem = Path(str(edoc.get("out", ""))).stem
                if out_stem == video_stem and edoc.get("subs") is not None:
                    return list(edoc.get("subs") or []), list(edoc.get("items") or [])
            except Exception:
                pass

    subs, items = [], {}
    if not log_path.is_file():
        return subs, []
    for line in log_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if m := re.match(r"^item(\d+) \[(\w+)\] ([\d.]+)~([\d.]+)s", line):
            t0, t1 = float(m[3]), float(m[4])
            items[int(m[1])] = {"n": int(m[1]), "type": m[2], "t0": t0, "dur": round(t1 - t0, 3), "shots": []}
        elif m := re.match(r"^item(\d+) shot(\d+): src ([\d.]+)~([\d.]+) → out ([\d.]+)~([\d.]+)\s*\((.*)\)", line):
            idx = int(m[1])
            if idx in items:
                items[idx]["shots"].append([float(m[5]), float(m[6]), m[7], "source.mp4"])
        elif m := re.match(r"^\s*\[최종 자막\] ([\d.]+)~([\d.]+) \([\d.]+s\): (.*)$", line):
            subs.append({"a": float(m[1]), "b": float(m[2]), "text": m[3]})
    exp_items = [items[k] for k in sorted(items)]
    return subs, exp_items


def extract_edl_hints(edl_path: Path | None, exp_items: list, subs: list | None = None):
    """EDL 에 수동 지정된 sfx / shot.sfx / circle / money icon 힌트를 정확한 출력 시각과 함께 추출."""
    hints = []
    if subs:
        for sb in subs:
            if isinstance(sb, dict) and sb.get("icon") == "money":
                hints.append((float(sb.get("a", 0.0)), "cash"))
                break
    if not edl_path or not edl_path.is_file():
        return hints
    try:
        edl = json.loads(edl_path.read_text(encoding="utf-8"))
    except Exception:
        return hints
    for idx, it in enumerate(edl.get("items") or []):
        t0 = exp_items[idx]["t0"] if idx < len(exp_items) else None
        if t0 is None:
            continue
        if it.get("sfx"):
            hints.append((float(t0) + float(it.get("sfx_offset", 0.0)), str(it["sfx"])))
        for sh_i, sh in enumerate(it.get("shots") or []):
            shots = exp_items[idx].get("shots", [])
            sh_entry = shots[sh_i] if sh_i < len(shots) else None
            sh_t = (sh_entry[0] if isinstance(sh_entry, list) else sh_entry.get("a", t0)) if sh_entry else t0
            if sh.get("sfx"):
                hints.append((float(sh_t), str(sh["sfx"])))
            if sh.get("circle"):
                c_obj = sh["circle"] if isinstance(sh["circle"], dict) else {}
                hints.append((float(sh_t), str(c_obj.get("sfx", "pop"))))
    return hints


def cmd_index(args):
    cfg = load_config()
    sfx_cfg = SFXConfig.from_env(repo_cfg=cfg)
    mode = args.mode
    if mode == "free":
        sfx_cfg.gemini_api_key = ""
        print(f"[무료 모드 · 0원] 파형·파일명 고속 색인 시작: {sfx_cfg.local_sfx_dir}")
        cat = SFXCatalogManager(sfx_cfg)
        stats = cat.sync_incremental()
        print(
            f"카탈로그 색인 완료: 총 {stats['total']}개 "
            f"(신규/갱신 +{stats['added_or_updated']}개, 캐시 유지 {stats.get('skipped_cached', 0)}개)"
        )
    elif mode == "gemini-free-tier":
        print(f"[Gemini 무료 티어 안전 속도] 8개 묶음 + 대기 간격 색인 시작: {sfx_cfg.local_sfx_dir}")
        cat = SFXCatalogManager(sfx_cfg)
        added = 0
        while True:
            stats = cat.sync_incremental(max_new_files=sfx_cfg.gemini_audio_batch_size)
            added += stats["added_or_updated"]
            print(f"  진행: 누적 신규 +{added}개 / 전체 {stats['total']}개")
            if stats["added_or_updated"] == 0:
                break
            time.sleep(4.5)
        print(f"카탈로그 색인 완료: 총 {stats['total']}개")
    else:
        print(f"[Gemini 멀티모달 청취] 색인 시작: {sfx_cfg.local_sfx_dir}")
        cat = SFXCatalogManager(sfx_cfg)
        stats = cat.sync_incremental()
        print(f"카탈로그 색인 완료: 총 {stats['total']}개 (신규/갱신 +{stats['added_or_updated']}개)")

    if sfx_cfg.local_sfx_dir.is_dir():
        print("기존 편집기 호환 목록(sfx_library.json) 동기화 중...")
        subprocess.run([sys.executable, "-u", "-m", "shorts.sfxlib"], cwd=ROOT, check=False)
    print(f"완료: 효과음 {len(cat.entries_by_rel_path)}개 준비됨")


def cmd_generate(args):
    job = JOBS / args.job
    vid = job / args.video
    edl_p = (job / args.edl) if args.edl else None
    cfg = load_config()
    sfx_cfg = SFXConfig.from_env(repo_cfg=cfg)
    preset = normalize_style_preset(args.style_preset or sfx_cfg.style_preset)
    sfx_cfg = sfx_cfg.with_style_preset(preset)
    spec = get_style_preset_spec(preset)
    backend = args.backend or sfx_cfg.resolved_backend
    if backend != "gemini-api":
        sfx_cfg.gemini_api_key = ""

    log_p = job / f"{vid.stem}_log.txt"
    if not log_p.is_file():
        meta = json.loads((job / f"{vid.stem}_meta.json").read_text(encoding="utf-8")) if (job / f"{vid.stem}_meta.json").is_file() else {}
        base_v = meta.get("sfx_base_video")
        if base_v and (job / f"{Path(base_v).stem}_log.txt").is_file():
            log_p = job / f"{Path(base_v).stem}_log.txt"

    subs, exp_items = parse_companion_log(log_p, job=job, video_stem=vid.stem)
    hints = extract_edl_hints(edl_p, exp_items, subs=subs)
    out_json = job / f"{vid.stem}_sfx_cuesheet.json"

    print(f"큐시트 자동 연출 시작 ({backend} · {spec['label_ko']}): {vid.name}")
    sheet = generate_sfx_cuesheet(
        video_path=vid,
        config=sfx_cfg,
        output_json_path=out_json,
        edl_hints=hints,
        edl_sub_list=subs or None,
        edl_items=exp_items or None,
        backend_override=backend,
        style_preset=preset,
    )
    print(f"완료: [{spec['label_ko']}] 효과음 큐 {len(sheet.cues)}개 생성 → {out_json.name}")


def cmd_apply(args):
    t_start = time.time()
    job = JOBS / args.job
    base_vid = job / args.base_video
    out_vid = job / args.out
    cue_path = job / args.cuesheet

    cfg = load_config()
    sfx_cfg = SFXConfig.from_env(repo_cfg=cfg)
    # Widen clamp bounds slightly during manual apply so user-edited dBs (-20 ~ -12) are preserved faithfully
    sfx_cfg.min_sfx_db = min(sfx_cfg.min_sfx_db, -20.0)
    sfx_cfg.max_sfx_db = max(sfx_cfg.max_sfx_db, -11.5)
    if sfx_cfg.resolved_backend != "gemini-api":
        sfx_cfg.gemini_api_key = ""

    print(f"효과음 카탈로그 확인 중 ({sfx_cfg.local_sfx_dir})...")
    cat = SFXCatalogManager(sfx_cfg)
    sync_stats = cat.sync_incremental()

    cuesheet = SFXCuesheet.from_dict(json.loads(cue_path.read_text(encoding="utf-8")))
    resolved = resolve_cuesheet(cuesheet, cat, sfx_cfg)
    print(f"매칭 완료: 요청 {len(cuesheet.cues)}개 → 합성 {len(resolved)}개")

    voice_stem = job / "edl_tmp" / f"{base_vid.stem}_voice.m4a"
    work_dir = job / "edl_tmp" / "sfx_remix"
    work_dir.mkdir(parents=True, exist_ok=True)

    clean_input = base_vid
    used_clean_stem = False
    if voice_stem.is_file():
        clean_input = work_dir / f"_clean_{base_vid.name}"
        subprocess.run(
            [
                "ffmpeg", "-y", "-v", "error",
                "-i", str(base_vid),
                "-i", str(voice_stem),
                "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "copy", "-c:a", "copy",
                str(clean_input),
            ],
            check=True,
        )
        used_clean_stem = True

    mixed_tmp = work_dir / f"_mixed_{out_vid.name}"
    mix_sfx_into_video(clean_input, mixed_tmp, resolved, cuesheet.video_duration_sec, sfx_cfg)

    edl_data = {}
    if args.edl and (job / args.edl).is_file():
        try:
            edl_data = json.loads((job / args.edl).read_text(encoding="utf-8"))
        except Exception:
            edl_data = {}
    bcfg = edl_data.get("bgm", cfg.get("bgm_default"))
    bgm_logs = []
    if used_clean_stem and bcfg and isinstance(bcfg, dict) and bcfg.get("file"):
        bgm_path = Path(bcfg["file"])
        bgm_path = bgm_path if bgm_path.is_absolute() else (ROOT / bgm_path)
        body_wav = job / "edl_tmp" / "body.mp4"
        export_json = job / "edl_tmp" / "export.json"
        master_db = 0.0
        if export_json.is_file():
            try:
                master_db = float(json.loads(export_json.read_text(encoding="utf-8")).get("master_db", 0.0))
            except Exception:
                master_db = 0.0
        if bgm_path.is_file() and (body_wav.is_file() or voice_stem.is_file()):
            try:
                from shorts import bgm as bgm_mod
                ref_voice = body_wav if body_wav.is_file() else voice_stem
                # voice_stem(_voice.m4a)은 이미 master_db 가 반영된 트랙이므로 중복 증폭 방지
                eff_master_db = master_db if body_wav.is_file() else 0.0
                _, bgm_logs = bgm_mod.apply(
                    ref_voice, mixed_tmp, out_vid, cuesheet.video_duration_sec,
                    bcfg, work_dir / "bgm", eff_master_db,
                    cfg.get("sfx_mix", {}).get("master_lufs", -14.0),
                )
            except Exception as exc:
                print(f"  참고: BGM 재적용 생략 ({exc}) → 효과음 합성본 사용")
                shutil.move(str(mixed_tmp), str(out_vid))
        else:
            shutil.move(str(mixed_tmp), str(out_vid))
    else:
        shutil.move(str(mixed_tmp), str(out_vid))

    out_stem = out_vid.stem
    out_cue_path = job / f"{out_stem}_sfx_cuesheet.json"
    cuesheet.video_path = str(out_vid)
    out_cue_path.write_text(json.dumps(cuesheet.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    report_payload = {
        "auto_sfx_enabled": True,
        "director_backend": sfx_cfg.resolved_backend,
        "style_preset": sfx_cfg.style_preset,
        "acquisition_mode": sfx_cfg.acquisition_mode,
        "catalog_sync": sync_stats,
        "input_video": str(base_vid),
        "output_video": str(out_vid),
        "used_clean_voice_stem": used_clean_stem,
        "cuesheet_path": str(out_cue_path),
        "cues_requested": len(cuesheet.cues),
        "cues_applied": len(resolved),
        "resolved_cues": [r.to_dict() for r in resolved],
    }
    (job / f"{out_stem}_sfx_mix_report.json").write_text(
        json.dumps(report_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    base_meta_p = job / f"{base_vid.stem}_meta.json"
    base_meta = json.loads(base_meta_p.read_text(encoding="utf-8")) if base_meta_p.is_file() else {}
    new_meta = {
        **base_meta,
        "edl": args.edl or base_meta.get("edl"),
        "duration": round(cuesheet.video_duration_sec, 2),
        "sfx_base_video": base_meta.get("sfx_base_video") or base_vid.name,
        "sfx_remixed": True,
    }
    (job / f"{out_stem}_meta.json").write_text(json.dumps(new_meta, ensure_ascii=False, indent=1), encoding="utf-8")

    base_log_p = job / f"{base_vid.stem}_log.txt"
    kept_lines = []
    if base_log_p.is_file():
        skip_sfx_block = False
        for ln in base_log_p.read_text(encoding="utf-8", errors="ignore").splitlines():
            if ln.startswith("효과음:") or ln.startswith("효과음(") or ln.startswith("자동 효과음 디렉터("):
                skip_sfx_block = True
                continue
            if skip_sfx_block and (ln.startswith("  ") or not ln.strip()):
                continue
            skip_sfx_block = False
            kept_lines.append(ln)

    sfx_lines = [
        f"자동 효과음 디렉터(웹에디터 리믹스/{sfx_cfg.acquisition_mode}): 큐 {len(resolved)}개 합성 → {out_cue_path.name}"
    ]
    for r in resolved:
        sfx_lines.append(
            f"  {r.cue.timestamp_sec:6.2f}s [{r.cue.sfx_category:8s}] {r.sfx.file_name[:32]:32s} "
            f"(피크보정 delay={r.insert_delay_ms}ms, trim={r.trim_start_sec:.2f}s, gain={r.effective_gain_db:+.1f}dB, {r.resolution_method})"
        )
    (job / f"{out_stem}_log.txt").write_text("\n".join(kept_lines + sfx_lines + bgm_logs), encoding="utf-8")

    base_subs_p = job / "edl_tmp" / f"{base_vid.stem}_subs.json"
    if base_subs_p.is_file():
        try:
            shutil.copy2(base_subs_p, job / "edl_tmp" / f"{out_stem}_subs.json")
        except Exception:
            pass

    export_p = job / "edl_tmp" / "export.json"
    if export_p.is_file():
        try:
            exp = json.loads(export_p.read_text(encoding="utf-8"))
            exp_master_db = float(exp.get("master_db", 0.0))
            exp["out"] = out_vid.name
            exp["sfx"] = [r.to_capcut_export_dict(master_db=exp_master_db) for r in resolved]
            export_p.write_text(json.dumps(exp, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception:
            pass

    elapsed = time.time() - t_start
    print(f"완료: {cuesheet.video_duration_sec:.2f}초 영상 · 효과음 {len(resolved)}개 합성 ({elapsed:.1f}초 소요)")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_idx = sub.add_parser("index")
    p_idx.add_argument("--mode", default="free", choices=["free", "gemini-free-tier", "gemini"])

    p_gen = sub.add_parser("generate")
    p_gen.add_argument("--job", required=True)
    p_gen.add_argument("--video", required=True)
    p_gen.add_argument("--edl", default="")
    p_gen.add_argument("--backend", default="auto")
    p_gen.add_argument("--style-preset", default="balanced")

    p_app = sub.add_parser("apply")
    p_app.add_argument("--job", required=True)
    p_app.add_argument("--base-video", required=True)
    p_app.add_argument("--cuesheet", required=True)
    p_app.add_argument("--out", required=True)
    p_app.add_argument("--edl", default="")

    args = ap.parse_args()
    if args.cmd == "index":
        cmd_index(args)
    elif args.cmd == "generate":
        cmd_generate(args)
    elif args.cmd == "apply":
        cmd_apply(args)


if __name__ == "__main__":
    main()
