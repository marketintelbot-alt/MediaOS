from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from .utils import (
    FPS,
    VIDEO_H,
    VIDEO_W,
    basic_peak_check,
    concat_list_escape,
    ffmpeg_filter_escape,
    ffprobe_json,
    has_audio_stream,
    media_duration,
    run_cmd,
    video_stream_info,
    which_any,
    write_text,
)

_FILTER_CACHE: dict[str, bool] = {}


def _image_segment_filter(duration: float, zoom: float) -> str:
    total_frames = max(1, int(round(duration * FPS)))
    zoom_target = min(max(1.02, zoom), 1.08)
    # Subtle punch-in over time; keep text crisp by rendering at target size and low compression.
    return (
        f"fps={FPS},"
        f"scale={VIDEO_W}:{VIDEO_H}:force_original_aspect_ratio=increase,"
        f"crop={VIDEO_W}:{VIDEO_H},"
        f"zoompan=z='if(lte(on,1),1.0,min(zoom+{(zoom_target - 1.0) / max(1,total_frames):.6f},{zoom_target:.3f}))':"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={VIDEO_W}x{VIDEO_H}:fps={FPS},"
        "format=yuv420p"
    )


def _video_segment_filter() -> str:
    return (
        f"fps={FPS},scale={VIDEO_W}:{VIDEO_H}:force_original_aspect_ratio=increase,"
        f"crop={VIDEO_W}:{VIDEO_H},"
        "eq=contrast=1.05:brightness=-0.005:saturation=0.90,"
        "unsharp=5:5:0.35:3:3:0.0,"
        "format=yuv420p"
    )


def _render_segment(segment: dict[str, Any], seg_out: Path, logger: Any = None) -> None:
    ffmpeg = which_any("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found")

    path = Path(segment["path"])
    dur = float(segment["duration"])
    kind = segment["kind"]
    zoom = float(segment.get("zoom") or 1.03)
    trim_start = max(0.0, float(segment.get("trim_start") or 0.0))

    if kind in {"slide", "image"}:
        cmd = [
            ffmpeg,
            "-y",
            "-loop",
            "1",
            "-i",
            str(path),
            "-t",
            f"{dur:.3f}",
            "-vf",
            _image_segment_filter(dur, zoom),
            "-r",
            str(FPS),
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "medium",
            "-crf",
            "16",
            str(seg_out),
        ]
    else:
        cmd = [
            ffmpeg,
            "-y",
            "-stream_loop",
            "-1",
            "-i",
            str(path),
        ]
        if trim_start > 0.0:
            cmd += ["-ss", f"{trim_start:.3f}"]
        cmd += [
            "-t",
            f"{dur:.3f}",
            "-vf",
            _video_segment_filter(),
            "-r",
            str(FPS),
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "medium",
            "-crf",
            "17",
            str(seg_out),
        ]
    run_cmd(cmd, logger=logger)


def _stitch_segments(segments_dir: Path, segment_paths: list[Path], out_video: Path, logger: Any = None) -> None:
    ffmpeg = which_any("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found")

    concat_file = segments_dir / "concat.txt"
    concat_lines = [f"file '{concat_list_escape(p)}'" for p in segment_paths]
    write_text(concat_file, "\n".join(concat_lines) + "\n")

    cmd = [
        ffmpeg,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(FPS),
        "-preset",
        "medium",
        "-crf",
        "16",
        str(out_video),
    ]
    run_cmd(cmd, logger=logger)


def _ffmpeg_has_filter(filter_name: str) -> bool:
    key = filter_name.strip().lower()
    if key in _FILTER_CACHE:
        return _FILTER_CACHE[key]
    ffmpeg = which_any("ffmpeg")
    if not ffmpeg:
        _FILTER_CACHE[key] = False
        return False
    cp = run_cmd([ffmpeg, "-hide_banner", "-filters"], check=False)
    text = (cp.stdout or "") + "\n" + (cp.stderr or "")
    found = bool(re.search(rf"\b{re.escape(key)}\b", text))
    _FILTER_CACHE[key] = found
    return found


def _drawtext_escape(text: str) -> str:
    s = text.replace("\\", "\\\\")
    s = s.replace(":", "\\:")
    s = s.replace("'", "\\'")
    s = s.replace("%", "\\%")
    s = s.replace(",", "\\,")
    s = s.replace("[", "\\[")
    s = s.replace("]", "\\]")
    s = s.replace("\n", " ")
    return s


def _pick_drawtext_fontfile() -> str | None:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    return None


def _drawtext_caption_filter(captions_ass: Path, logger: Any = None) -> str:
    events_json = captions_ass.with_suffix(".json")
    if not events_json.exists():
        raise RuntimeError("Caption fallback JSON not found for drawtext burn-in")
    events = json.loads(events_json.read_text(encoding="utf-8"))
    if not isinstance(events, list) or not events:
        raise RuntimeError("Caption fallback JSON is empty")

    fontfile = _pick_drawtext_fontfile()
    filters = ["format=yuv420p"]
    for i, ev in enumerate(events):
        try:
            start = max(0.0, float(ev.get("start", 0.0)))
            end = max(start + 0.2, float(ev.get("end", start + 0.2)))
            text = str(ev.get("text", "")).strip()
        except Exception:
            continue
        if not text:
            continue
        opts: list[str] = []
        if fontfile:
            opts.append(f"fontfile='{ffmpeg_filter_escape(fontfile)}'")
        opts.extend(
            [
                f"text='{_drawtext_escape(text)}'",
                "fontsize=58",
                "fontcolor=#E8EEF6",
                "x=(w-text_w)/2",
                "y=1560-text_h/2",
                "borderw=3",
                "bordercolor=#101010",
                "shadowx=1",
                "shadowy=1",
                "shadowcolor=#000000",
                "line_spacing=4",
                "fix_bounds=1",
                f"enable='between(t\\,{start:.3f}\\,{end:.3f})'",
            ]
        )
        filters.append("drawtext=" + ":".join(opts))
    if logger:
        logger.warn("FFmpeg build lacks libass/subtitles; using drawtext caption fallback (reduced caption styling)")
    return ",".join(filters)


def _burn_captions_and_mux(
    stitched_video: Path,
    mixed_audio: Path,
    captions_ass: Path,
    final_mp4: Path,
    target_length: int,
    logger: Any = None,
    safe_mode: bool = False,
) -> None:
    ffmpeg = which_any("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found")

    if _ffmpeg_has_filter("subtitles"):
        vf = f"subtitles=filename='{ffmpeg_filter_escape(captions_ass)}'"
    else:
        vf = _drawtext_caption_filter(captions_ass, logger=logger)
    audio_filter = "volume=-2dB" if safe_mode else "anull"
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(stitched_video),
        "-i",
        str(mixed_audio),
        "-vf",
        vf,
        "-af",
        audio_filter,
        "-r",
        str(FPS),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-preset",
        "medium",
        "-crf",
        "16",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-t",
        str(target_length),
        "-movflags",
        "+faststart",
        "-metadata",
        "comment=TV_CAPTIONS_BURNED=1",
        str(final_mp4),
    ]
    run_cmd(cmd, logger=logger)


def _copy_thumbnail(thumbnail_source: Path, thumbnail_out: Path, logger: Any = None) -> None:
    thumbnail_out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(thumbnail_source, thumbnail_out)
    if logger:
        logger.step(f"Thumbnail generated from {thumbnail_source.name}")


def self_check_render(
    reel_mp4: Path,
    captions_ass: Path,
    logger: Any = None,
) -> dict[str, Any]:
    errors: list[str] = []
    checks: dict[str, Any] = {}

    info = ffprobe_json(reel_mp4)
    vstream = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), {})
    width = int(vstream.get("width") or 0)
    height = int(vstream.get("height") or 0)
    duration = float((info.get("format") or {}).get("duration") or 0.0)
    checks["width"] = width
    checks["height"] = height
    checks["duration"] = duration

    if width != VIDEO_W or height != VIDEO_H:
        errors.append(f"Resolution mismatch: {width}x{height}")
    if not (20.0 <= duration <= 35.0):
        errors.append(f"Duration out of range: {duration:.2f}s")
    if not has_audio_stream(reel_mp4):
        errors.append("Missing audio stream")

    peak_ok, peak_db = basic_peak_check(reel_mp4, logger=logger)
    checks["peak_db"] = peak_db
    if peak_db is not None and not peak_ok:
        errors.append(f"Audio peak too high / clipping risk: {peak_db:.2f} dB")

    comment = str(((info.get("format") or {}).get("tags") or {}).get("comment", ""))
    captions_flag = "TV_CAPTIONS_BURNED=1" in comment and captions_ass.exists() and captions_ass.stat().st_size > 0
    checks["captions_burned"] = captions_flag
    if not captions_flag:
        errors.append("Captions burned-in check failed")

    ok = not errors
    checks["ok"] = ok
    checks["errors"] = errors
    if logger:
        logger.step(
            "Self-check: "
            + ("PASS" if ok else "FAIL")
            + f" (res={width}x{height}, dur={duration:.2f}s, peak={peak_db if peak_db is not None else 'n/a'} dB, captions={captions_flag})"
        )
        for err in errors:
            logger.warn(err)
    return checks


def render_reel_with_retry(
    storyboard: dict[str, Any],
    mixed_audio: Path,
    captions_ass: Path,
    output_dir: Path,
    work_dir: Path,
    logger: Any = None,
) -> dict[str, Any]:
    target_length = int(storyboard["target_length"])
    segments = storyboard["segments"]
    thumbnail_source = Path(storyboard["thumbnail_source"])

    segments_dir = work_dir / "segments"
    segments_dir.mkdir(parents=True, exist_ok=True)
    stitched_video = work_dir / "stitched.mp4"
    final_mp4 = output_dir / "reel.mp4"
    thumbnail_png = output_dir / "thumbnail.png"

    for attempt in (1, 2):
        safe_mode = attempt == 2
        if logger:
            logger.step(f"Render attempt {attempt}/2 ({'safe mode' if safe_mode else 'normal mode'})")

        # rebuild segment clips each attempt to ensure deterministic final timing if previous run was interrupted
        segment_paths: list[Path] = []
        for seg in segments:
            seg_out = segments_dir / f"seg_{int(seg['index']):03d}.mp4"
            _render_segment(seg, seg_out, logger=logger)
            segment_paths.append(seg_out)

        _stitch_segments(segments_dir, segment_paths, stitched_video, logger=logger)
        _burn_captions_and_mux(
            stitched_video,
            mixed_audio,
            captions_ass,
            final_mp4,
            target_length=target_length,
            logger=logger,
            safe_mode=safe_mode,
        )
        _copy_thumbnail(thumbnail_source, thumbnail_png, logger=logger)
        checks = self_check_render(final_mp4, captions_ass, logger=logger)
        if checks["ok"]:
            return {"reel": final_mp4, "thumbnail": thumbnail_png, "checks": checks}
        if attempt == 1 and logger:
            logger.warn("Self-check failed; automatically re-rendering once with corrected settings")

    raise RuntimeError("Render self-check failed after one automatic re-render")
