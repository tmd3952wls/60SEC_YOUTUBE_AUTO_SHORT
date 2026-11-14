"""End-to-end Auto SFX Director Orchestrator, EDL/Render/WebEditor Hooks & CLI."""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .cataloger import SFXCatalogManager
from .config import SFXConfig, normalize_style_preset
from .cuesheet import generate_sfx_cuesheet
from .matcher import calibrate_resolved_cues_to_voice, resolve_cuesheet
from .mixer import mix_sfx_into_video
from .models import SFXCuesheet

logger = logging.getLogger("auto_sfx.director")


def apply_auto_sfx_if_enabled(
    draft_video_path: str | Path,
    output_video_path: str | Path | None = None,
    subtitle_path: str | Path | None = None,
    env_path: str | Path | None = None,
    cuesheet_override_path: str | Path | None = None,
    cuesheet_out_path: str | Path | None = None,
    edl_hints: List[Tuple[float, str]] | None = None,
    repo_cfg: Dict[str, Any] | None = None,
    backend_override: str | None = None,
    style_preset: str | None = None,
    offline_catalog: bool = False,
) -> Dict[str, Any]:
    """Universal post-render hook for shorts/render.py, Web Editor 2-second remix, and standalone CLI."""
    draft_path = Path(draft_video_path)
    if not draft_path.is_file():
        raise FileNotFoundError(f"Draft video not found: {draft_path}")

    out_path = Path(output_video_path) if output_video_path else draft_path.with_name(f"{draft_path.stem}_sfx.mp4")
    config = SFXConfig.from_env(Path(env_path) if env_path else None, repo_cfg=repo_cfg)
    if style_preset:
        config = config.with_style_preset(style_preset)

    saved_key = config.gemini_api_key
    if offline_catalog or config.resolved_backend == "local-free" or (backend_override and backend_override.strip().lower() == "local-free"):
        config.gemini_api_key = ""

    if not config.auto_sfx_enabled and not cuesheet_override_path:
        if draft_path.resolve() != out_path.resolve():
            out_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(draft_path, out_path)
        return {
            "auto_sfx_enabled": False,
            "director_backend": config.resolved_backend,
            "style_preset": config.style_preset,
            "acquisition_mode": config.acquisition_mode,
            "input_video": str(draft_path),
            "output_video": str(out_path),
            "cues_applied": 0,
            "resolved_cues": [],
        }

    catalog = SFXCatalogManager(config)
    sync_stats = catalog.sync_incremental()

    if backend_override == "gemini-api" and saved_key:
        config.gemini_api_key = saved_key

    sub_p = Path(subtitle_path) if subtitle_path else None
    if cuesheet_override_path:
        cuesheet_file = Path(cuesheet_override_path)
        cuesheet = SFXCuesheet.from_dict(json.loads(cuesheet_file.read_text(encoding="utf-8")))
    else:
        cuesheet_file = Path(cuesheet_out_path) if cuesheet_out_path else (config.cuesheet_dir / f"{out_path.stem}_sfx_cuesheet.json")
        cuesheet = generate_sfx_cuesheet(
            draft_path,
            config,
            output_json_path=cuesheet_file,
            subtitle_path=sub_p,
            edl_hints=edl_hints,
            backend_override=backend_override,
            style_preset=config.style_preset,
        )

    resolved = resolve_cuesheet(cuesheet, catalog, config)
    calibrate_resolved_cues_to_voice(draft_path, resolved, ffmpeg_bin=config.ffmpeg_bin)

    report_path = out_path.with_name(f"{out_path.stem}_sfx_mix_report.json")
    report_payload = {
        "auto_sfx_enabled": True,
        "director_backend": backend_override or config.resolved_backend,
        "style_preset": config.style_preset,
        "acquisition_mode": config.acquisition_mode,
        "catalog_sync": sync_stats,
        "input_video": str(draft_path),
        "output_video": str(out_path),
        "cuesheet_path": str(cuesheet_file),
        "cues_requested": len(cuesheet.cues),
        "cues_applied": len(resolved),
        "resolved_cues": [r.to_dict() for r in resolved],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if draft_path.resolve() == out_path.resolve():
        tmp_out = out_path.with_name(f"{out_path.stem}.__sfx_tmp__.mp4")
        mix_sfx_into_video(draft_path, tmp_out, resolved, cuesheet.video_duration_sec, config)
        tmp_out.replace(out_path)
    else:
        mix_sfx_into_video(draft_path, out_path, resolved, cuesheet.video_duration_sec, config)

    report_payload["mix_report_path"] = str(report_path)
    return report_payload


def run_edl_auto_sfx_stage(
    job: Path,
    video: Path,
    total: float,
    edl_hints: List[Tuple[float, str]],
    sub_list: List[Dict[str, Any]],
    exp_items: List[Dict[str, Any]],
    master_db: float,
    repo_cfg: Dict[str, Any] | None = None,
) -> Tuple[List[Dict[str, Any]], float, List[str]]:
    """Native integration stage for shorts/edl.py (runs right after subtitle/circle burn-in and before bgm.py)."""
    config = SFXConfig.from_env(repo_cfg=repo_cfg)
    backend = config.resolved_backend
    if backend != "gemini-api":
        config.gemini_api_key = ""

    catalog = SFXCatalogManager(config)
    sync_stats = catalog.sync_incremental()

    stem = video.stem
    cuesheet_path = job / f"{stem}_sfx_cuesheet.json"
    cuesheet = generate_sfx_cuesheet(
        video_path=video,
        config=config,
        output_json_path=cuesheet_path,
        edl_hints=edl_hints,
        edl_sub_list=sub_list,
        edl_items=exp_items,
        backend_override=backend,
        style_preset=config.style_preset,
    )
    resolved = resolve_cuesheet(cuesheet, catalog, config)
    calibrate_resolved_cues_to_voice(video, resolved, ffmpeg_bin=config.ffmpeg_bin)

    report_path = job / f"{stem}_sfx_mix_report.json"
    report_path.write_text(
        json.dumps(
            {
                "director_backend": backend,
                "style_preset": config.style_preset,
                "mode": config.acquisition_mode,
                "catalog_sync": sync_stats,
                "cuesheet_path": str(cuesheet_path),
                "cues_applied": len(resolved),
                "resolved_cues": [r.to_dict() for r in resolved],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    tmp_out = job / f"_autosfx_{video.name}"
    mix_sfx_into_video(video, tmp_out, resolved, total, config)
    tmp_out.replace(video)

    exp_sfx = [r.to_capcut_export_dict(master_db=master_db) for r in resolved]
    log_lines = [
        f"자동 효과음 디렉터({backend}/{config.style_preset}/{config.acquisition_mode}): 카탈로그 {sync_stats['total']}개(신규 +{sync_stats['added_or_updated']}), 큐 {len(resolved)}개 합성 → {cuesheet_path.name}"
    ]
    for r in resolved:
        log_lines.append(
            f"  {r.cue.timestamp_sec:6.2f}s [{r.cue.sfx_category:8s}] {r.sfx.file_name[:32]:32s} "
            f"(피크보정 delay={r.insert_delay_ms}ms, trim={r.trim_start_sec:.2f}s, gain={r.effective_gain_db:+.1f}dB, {r.resolution_method})"
        )
    return exp_sfx, master_db, log_lines


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="60SEC YouTube Auto Short — Automated SFX Director CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_index = sub.add_parser("index", help="Incrementally index LOCAL_SFX_DIR (2,869+ files) into assets/sfx_catalog.json")
    p_index.add_argument("--sfx-dir", type=str, default=None, help="Override LOCAL_SFX_DIR")
    p_index.add_argument("--offline", action="store_true", help="Zero-cost (0 KRW) fast acoustic + filename indexing without Gemini API")
    p_index.add_argument("--free-tier-safe", action="store_true", help="Add 4.5s pause between Gemini batches to stay within AI Studio Free Tier RPM")
    p_index.add_argument("--max-new", type=int, default=None, help="Cap newly analyzed files in this run")
    p_index.add_argument("--no-prune", action="store_true", help="Keep missing files in catalog")

    p_cue = sub.add_parser("cuesheet", help="Generate sfx_cuesheet.json for a rendered Short MP4")
    p_cue.add_argument("--video", type=str, required=True, help="Draft MP4 path")
    p_cue.add_argument("--edl", type=str, default=None, help="Optional companion vN_edl.json for exact subtitle/shot context")
    p_cue.add_argument("--subtitles", type=str, default=None, help="Optional .srt/.ass/.vtt/.json subtitle file")
    p_cue.add_argument("--backend", type=str, default=None, choices=["auto", "local-free", "agy-cli", "gemini-api"])
    p_cue.add_argument("--preset", type=str, default=None, help="Intensity/density preset: clean | balanced | punchy")
    p_cue.add_argument("--out", type=str, default=None, help="Output cuesheet JSON path")

    p_run = sub.add_parser("run", help="Run Auto SFX Director pipeline (index -> cuesheet -> match/acquire -> lossless FFmpeg mix)")
    p_run.add_argument("--video", type=str, required=True, help="Draft MP4 input path")
    p_run.add_argument("--subtitles", type=str, default=None, help="Optional .srt/.ass/.vtt/.json subtitle file")
    p_run.add_argument("--output", type=str, default=None, help="Final MP4 output path")
    p_run.add_argument("--in-place", action="store_true", help="Overwrite input MP4 safely after mixing")
    p_run.add_argument("--cuesheet", type=str, default=None, help="Optional pre-edited sfx_cuesheet.json path")
    p_run.add_argument("--backend", type=str, default=None, choices=["auto", "local-free", "agy-cli", "gemini-api"])
    p_run.add_argument("--preset", type=str, default=None, help="Intensity/density preset: clean | balanced | punchy")
    p_run.add_argument("--offline-catalog", action="store_true", help="Force 0-cost offline catalog sync")

    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(name)s: %(message)s")
    args = _build_parser().parse_args(argv)
    config = SFXConfig.from_env()

    if args.command == "index":
        if args.sfx_dir:
            config.local_sfx_dir = Path(args.sfx_dir)
        if args.offline:
            config.gemini_api_key = ""
        if args.free_tier_safe and config.gemini_api_key:
            catalog = SFXCatalogManager(config)
            total_added = 0
            while True:
                stats = catalog.sync_incremental(prune_missing=not args.no_prune, max_new_files=config.gemini_audio_batch_size)
                total_added += stats["added_or_updated"]
                if stats["added_or_updated"] == 0 or (args.max_new and total_added >= args.max_new):
                    print(json.dumps({"mode": "gemini_free_tier_safe", "catalog_path": str(config.catalog_path), "total": stats["total"], "added_or_updated": total_added}, ensure_ascii=False, indent=2))
                    return 0
                time.sleep(4.5)
        catalog = SFXCatalogManager(config)
        stats = catalog.sync_incremental(prune_missing=not args.no_prune, max_new_files=args.max_new)
        print(json.dumps({"mode": "offline_free" if args.offline or not config.gemini_api_key else "gemini_multimodal", "catalog_path": str(config.catalog_path), **stats}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "cuesheet":
        out_json = Path(args.out) if args.out else None
        sub_p = Path(args.subtitles) if args.subtitles else None
        edl_subs = None
        edl_items = None
        vid_p = Path(args.video)
        subs_json_p = vid_p.parent / "edl_tmp" / f"{vid_p.stem}_subs.json"
        exp_json_p = vid_p.parent / "edl_tmp" / "export.json"
        if subs_json_p.is_file():
            try:
                sdoc = json.loads(subs_json_p.read_text(encoding="utf-8"))
                edl_subs = sdoc.get("subs")
                edl_items = sdoc.get("items")
            except Exception:
                pass
        elif exp_json_p.is_file():
            try:
                edoc = json.loads(exp_json_p.read_text(encoding="utf-8"))
                if edoc.get("out") == vid_p.name:
                    edl_subs = edoc.get("subs")
                    edl_items = edoc.get("items")
            except Exception:
                pass
        if edl_subs is None and args.edl and Path(args.edl).is_file():
            log_p = vid_p.with_name(f"{vid_p.stem}_log.txt")
            if log_p.is_file():
                import re as _re
                edl_subs = []
                for ln in log_p.read_text(encoding="utf-8", errors="ignore").splitlines():
                    if m := _re.match(r"^\s*\[최종 자막\] ([\d.]+)~([\d.]+) \([\d.]+s\): (.*)$", ln):
                        edl_subs.append({"a": float(m[1]), "b": float(m[2]), "text": m[3]})
        preset = normalize_style_preset(args.preset) if args.preset else config.style_preset
        sheet = generate_sfx_cuesheet(
            vid_p,
            config,
            output_json_path=out_json,
            subtitle_path=sub_p,
            edl_sub_list=edl_subs,
            edl_items=edl_items,
            backend_override=args.backend,
            style_preset=preset,
        )
        print(json.dumps(sheet.to_dict(), ensure_ascii=False, indent=2))
        return 0

    if args.command == "run":
        target_out = Path(args.video) if args.in_place else (Path(args.output) if args.output else None)
        result = apply_auto_sfx_if_enabled(
            draft_video_path=args.video,
            output_video_path=target_out,
            subtitle_path=args.subtitles,
            cuesheet_override_path=args.cuesheet,
            backend_override=args.backend,
            style_preset=args.preset,
            offline_catalog=args.offline_catalog,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
