#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from modules.audio_mix import mix_audio
from modules.broll_select import scan_broll_library, select_broll
from modules.caption_writer import build_caption_text, build_hooks_text
from modules.captions import generate_ass_captions
from modules.idea_to_script import generate_script
from modules.render import render_reel_with_retry
from modules.slides import ensure_brand_assets, generate_tradevera_slides
from modules.storyboard import build_storyboard
from modules.tts import synthesize_voice
from modules.utils import BuildLogger, choose_length, ensure_dir, parse_image_inputs, timestamp_slug, write_json, write_text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TradeVera Reels Factory (offline, free stack)")
    parser.add_argument("--idea", required=True, help="Reel idea text")
    parser.add_argument("--images", nargs="*", default=None, help="Optional image path(s) or globs (0-12)")
    parser.add_argument("--style", default="tradevera_premium", help="Style preset name (default: tradevera_premium)")
    parser.add_argument("--no_broll", action="store_true", help="Use only generated slides + user images")
    parser.add_argument("--length", type=int, default=None, help="Target duration (20-35 sec). Default random 22-30")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = Path(__file__).resolve().parent
    logger = BuildLogger()
    logger.step("tradevera-reels-factory build started")
    logger.add_versions()

    output_dir = ensure_dir(project_root / "outputs" / timestamp_slug())
    work_dir = ensure_dir(output_dir / "_work")
    slides_dir = ensure_dir(work_dir / "slides")
    audio_dir = ensure_dir(work_dir / "audio")
    captions_dir = ensure_dir(work_dir / "captions")

    build_log_path = output_dir / "build_log.txt"

    try:
        if args.style != "tradevera_premium":
            logger.warn(f"Unsupported style preset '{args.style}'; using tradevera_premium")
            args.style = "tradevera_premium"

        target_length = choose_length(args.length)
        logger.step(f"Target length: {target_length}s")

        brand = ensure_brand_assets(project_root, logger=logger)
        palette = brand["palette"]

        user_images = parse_image_inputs(args.images)
        if user_images:
            logger.step(f"User images loaded: {len(user_images)}")
        else:
            logger.step("No user images provided; using generated TradeVera slides only")

        script = generate_script(args.idea, target_length=target_length, style=args.style)
        script_json_path = output_dir / "script.json"
        write_json(script_json_path, script)
        write_text(output_dir / "caption.txt", build_caption_text(script))
        write_text(output_dir / "hooks.txt", build_hooks_text(script))
        logger.step("Script JSON, caption text, and hooks generated")

        slide_paths = generate_tradevera_slides(slides_dir, script, project_root, logger=logger)
        logger.step(f"Generated {len(slide_paths)} TradeVera slide templates")

        broll_library = scan_broll_library(project_root / "assets" / "broll")
        selected_broll = select_broll(broll_library, script["idea"], max_items=8, no_broll=args.no_broll)
        if args.no_broll:
            logger.step("--no_broll enabled; skipping local b-roll library")
        elif selected_broll:
            logger.step(f"Selected {len(selected_broll)} local b-roll clip(s)")
        else:
            logger.step("No local b-roll found; reel will use slides and user images only")

        storyboard = build_storyboard(
            script=script,
            user_images=user_images,
            slide_paths=slide_paths,
            broll_clips=selected_broll,
            target_length=target_length,
            no_broll=args.no_broll,
        )
        logger.step(f"Storyboard ready: {len(storyboard['segments'])} cuts, ~{storyboard['estimated_duration']}s")

        voice_wav = audio_dir / "voice.wav"
        tts_meta = synthesize_voice(script["narration"], voice_wav, project_root, logger=logger)
        logger.step(f"Voiceover generated ({tts_meta['engine']})")

        captions_ass = captions_dir / "captions.ass"
        caption_meta = generate_ass_captions(script["narration"], voice_wav, captions_ass, palette, logger=logger)
        logger.step(f"Caption mode: {caption_meta['mode']}")

        mixed_audio = audio_dir / "mixed.wav"
        mix_meta = mix_audio(
            voice_wav=voice_wav,
            output_wav=mixed_audio,
            target_length=target_length,
            project_root=project_root,
            sfx_events=storyboard.get("sfx_events") or [],
            logger=logger,
            safe_mode=False,
        )
        logger.step("Audio mix generated")

        render_meta = render_reel_with_retry(
            storyboard=storyboard,
            mixed_audio=mixed_audio,
            captions_ass=captions_ass,
            output_dir=output_dir,
            work_dir=work_dir,
            logger=logger,
        )
        logger.step("Final reel render completed")

        # Persist a concise production summary into build_log.
        logger.step(f"Output reel: {render_meta['reel'].name}")
        logger.step(f"Output thumbnail: {render_meta['thumbnail'].name}")
        if mix_meta.get("music"):
            logger.step(f"Music source: {Path(str(mix_meta['music'])).name}")
        else:
            logger.step("Music source: none (voice-only)")

        logger.write(build_log_path)
        print(f"SUCCESS: {output_dir}")
        return 0
    except Exception as exc:
        logger.warn(f"Build failed: {exc}")
        logger.write(build_log_path)
        print(f"ERROR: {exc}", file=sys.stderr)
        print(f"Build log: {build_log_path}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
