from __future__ import annotations

import random
from pathlib import Path
from typing import Any

from .utils import clamp, seed_from_text


SLIDE_SEQUENCE_KEYS = [
    "title_card",
    "three_rules_widget",
    "myth_vs_fact",
    "do_this_not_that",
    "mini_chart",
    "checklist",
    "setup_vs_noise",
    "risk_formula",
]


def _normalize_durations(durations: list[float], target_total: float) -> list[float]:
    if not durations:
        return []
    cur = sum(durations)
    if cur <= 0:
        return durations
    scale = target_total / cur
    out = [clamp(d * scale, 0.6, 2.0) for d in durations]
    diff = target_total - sum(out)
    i = 0
    # distribute remaining milliseconds while respecting shot max/min
    while abs(diff) > 0.01 and i < 5000:
        idx = i % len(out)
        step = 0.02 if diff > 0 else -0.02
        nxt = out[idx] + step
        if 0.6 <= nxt <= 2.0:
            out[idx] = round(nxt, 2)
            diff -= step
        i += 1
    return out


def build_storyboard(
    script: dict[str, Any],
    user_images: list[Path],
    slide_paths: dict[str, Path],
    broll_clips: list[dict[str, Any]],
    target_length: int,
    no_broll: bool = False,
) -> dict[str, Any]:
    idea = script.get("idea", "")
    rnd = random.Random(seed_from_text(f"storyboard|{idea}|{target_length}"))

    desired_segments = max(16, min(28, int(round(target_length / 1.1))))
    base_durations = [rnd.uniform(0.75, 1.45) for _ in range(desired_segments)]
    if desired_segments >= 2:
        base_durations[0] = 1.8  # hook emphasis
        base_durations[-1] = 1.6  # CTA emphasis
    durations = _normalize_durations(base_durations, float(target_length))

    slides_cycle = [slide_paths[k] for k in SLIDE_SEQUENCE_KEYS if k in slide_paths]
    if not slides_cycle:
        raise RuntimeError("No generated slides available for storyboard")

    media_pool: list[tuple[str, Path]] = [("slide", p) for p in slides_cycle]
    if user_images:
        media_pool.extend(("image", p) for p in user_images)
    if not no_broll and broll_clips:
        media_pool.extend(("video", Path(c["path"])) for c in broll_clips if c.get("path"))

    segments: list[dict[str, Any]] = []
    total = 0.0
    slide_index = 0
    image_index = 0
    video_index = 0
    image_paths = list(user_images)
    video_paths = [Path(c["path"]) for c in broll_clips] if (not no_broll and broll_clips) else []

    for idx, dur in enumerate(durations):
        if idx == 0 and "title_card" in slide_paths:
            kind, path = "slide", slide_paths["title_card"]
        elif idx == len(durations) - 1 and "checklist" in slide_paths:
            kind, path = "slide", slide_paths["checklist"]
        else:
            choice_roll = rnd.random()
            if image_paths and choice_roll < 0.28:
                kind, path = "image", image_paths[image_index % len(image_paths)]
                image_index += 1
            elif video_paths and choice_roll < 0.55:
                kind, path = "video", video_paths[video_index % len(video_paths)]
                video_index += 1
            else:
                kind, path = "slide", slides_cycle[slide_index % len(slides_cycle)]
                slide_index += 1

        zoom = round(rnd.uniform(1.02, 1.08), 3) if kind in {"slide", "image"} else 1.0
        segments.append(
            {
                "index": idx,
                "kind": kind,
                "path": str(path),
                "duration": round(float(dur), 2),
                "zoom": zoom,
            }
        )
        total += float(dur)

    # SFX pattern breaks: hook and CTA markers, plus a mid-point if long enough.
    sfx_events = [{"time": 0.0, "type": "hook_hit"}]
    if len(segments) >= 8:
        sfx_events.append({"time": round(sum(d["duration"] for d in segments[: len(segments) // 2]), 2), "type": "transition"})
    sfx_events.append({"time": max(0.0, round(total - 1.2, 2)), "type": "cta"})

    return {
        "segments": segments,
        "target_length": target_length,
        "estimated_duration": round(total, 2),
        "sfx_events": sfx_events,
        "thumbnail_source": str(slide_paths.get("title_card", slides_cycle[0])),
    }
