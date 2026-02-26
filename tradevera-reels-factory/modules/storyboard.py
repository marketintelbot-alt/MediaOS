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

    desired_segments = max(16, min(28, int(round(target_length / 1.03))))
    base_durations: list[float] = []
    for idx in range(desired_segments):
        phase = idx / max(1, desired_segments - 1)
        if phase < 0.12:
            dur = rnd.uniform(0.65, 1.15)
        elif phase < 0.65:
            dur = rnd.uniform(0.7, 1.25)
        elif phase < 0.9:
            dur = rnd.uniform(0.85, 1.4)
        else:
            dur = rnd.uniform(0.95, 1.55)
        base_durations.append(dur)
    if desired_segments >= 2:
        base_durations[0] = 1.7  # hook emphasis
        base_durations[-1] = 1.75  # CTA emphasis
    durations = _normalize_durations(base_durations, float(target_length))

    slides_cycle = [
        slide_paths[k]
        for k in SLIDE_SEQUENCE_KEYS
        if k in slide_paths and k not in {"title_card", "checklist"}
    ]
    if not slides_cycle:
        slides_cycle = [slide_paths[k] for k in SLIDE_SEQUENCE_KEYS if k in slide_paths]
    if not slides_cycle:
        raise RuntimeError("No generated slides available for storyboard")

    segments: list[dict[str, Any]] = []
    total = 0.0
    slide_index = 0
    image_index = 0
    video_index = 0
    image_paths = list(user_images)
    video_items = list(broll_clips) if (not no_broll and broll_clips) else []
    visual_plan_templates = [
        str(item.get("template"))
        for item in (script.get("visual_plan") or [])
        if str(item.get("template") or "") in slide_paths
    ]
    anchor_positions: list[int] = [0]
    if desired_segments >= 8:
        anchor_positions.extend(
            [
                max(1, int(round(desired_segments * 0.18))),
                max(2, int(round(desired_segments * 0.36))),
                max(3, int(round(desired_segments * 0.56))),
                max(4, int(round(desired_segments * 0.76))),
            ]
        )
    anchor_positions.append(desired_segments - 1)
    anchor_positions = sorted({p for p in anchor_positions if 0 <= p < desired_segments})
    anchor_map: dict[int, tuple[str, Path]] = {}
    for pos, tmpl in zip(anchor_positions, visual_plan_templates):
        anchor_map[pos] = ("slide", slide_paths[tmpl])
    if "title_card" in slide_paths:
        anchor_map[0] = ("slide", slide_paths["title_card"])
    if "checklist" in slide_paths:
        anchor_map[desired_segments - 1] = ("slide", slide_paths["checklist"])

    last_path: str | None = None
    kind_run = 0
    last_kind: str | None = None
    slide_run = 0
    video_run = 0
    image_run = 0

    def _pick_slide_path(prefer_template: str | None = None) -> Path:
        nonlocal slide_index, last_path
        if prefer_template and prefer_template in slide_paths:
            candidate = slide_paths[prefer_template]
            if str(candidate) != last_path or len(slides_cycle) == 1:
                return candidate
        attempts = 0
        while attempts < len(slides_cycle) + 3:
            candidate = slides_cycle[slide_index % len(slides_cycle)]
            slide_index += 1
            if str(candidate) != last_path or len(slides_cycle) == 1:
                return candidate
            attempts += 1
        return slides_cycle[(slide_index - 1) % len(slides_cycle)]

    for idx, dur in enumerate(durations):
        if idx in anchor_map:
            kind, path = anchor_map[idx]
        else:
            # Weighted selection with anti-repeat logic to reduce robotic slide runs.
            can_image = bool(image_paths) and image_run < 2
            can_video = bool(video_items) and video_run < 2
            can_slide = slide_run < (3 if (image_paths or video_items) else 6)
            phase = idx / max(1, len(durations) - 1)
            image_weight = 0.20 if can_image else 0.0
            video_weight = 0.36 if can_video else 0.0
            slide_weight = 0.44 if can_slide else 0.0
            if phase < 0.15:
                slide_weight += 0.18
                video_weight *= 0.8
            elif phase > 0.7:
                slide_weight += 0.08
                image_weight += 0.05
            if last_kind == "slide":
                slide_weight *= 0.72
            if last_kind == "video":
                video_weight *= 0.78
            if last_kind == "image":
                image_weight *= 0.78

            total_w = slide_weight + image_weight + video_weight
            if total_w <= 0:
                kind, path = "slide", _pick_slide_path()
            else:
                roll = rnd.random() * total_w
                if roll < image_weight and image_paths:
                    kind = "image"
                    attempts = 0
                    path = image_paths[image_index % len(image_paths)]
                    while str(path) == last_path and attempts < len(image_paths):
                        image_index += 1
                        path = image_paths[image_index % len(image_paths)]
                        attempts += 1
                    image_index += 1
                elif roll < image_weight + video_weight and video_items:
                    kind = "video"
                    attempts = 0
                    item = video_items[video_index % len(video_items)]
                    path = Path(item["path"])
                    while str(path) == last_path and attempts < len(video_items):
                        video_index += 1
                        item = video_items[video_index % len(video_items)]
                        path = Path(item["path"])
                        attempts += 1
                    video_index += 1
                else:
                    kind, path = "slide", _pick_slide_path()

        zoom = round(rnd.uniform(1.02, 1.08), 3) if kind in {"slide", "image"} else 1.0
        if idx in anchor_map and kind == "slide":
            zoom = round(rnd.uniform(1.01, 1.05), 3)
        seg = {
            "index": idx,
            "kind": kind,
            "path": str(path),
            "duration": round(float(dur), 2),
            "zoom": zoom,
        }
        if kind == "video":
            # Randomize source offsets so repeated b-roll clips do not always start from frame 0.
            clip_meta = next((c for c in video_items if str(Path(c.get("path", ""))) == str(path)), None)
            clip_dur = 0.0
            try:
                clip_dur = float((clip_meta or {}).get("duration") or 0.0)
            except Exception:
                clip_dur = 0.0
            max_start = max(0.0, clip_dur - float(dur) - 0.08)
            if max_start > 0.25:
                seg["trim_start"] = round(rnd.uniform(0.0, max_start), 3)
        segments.append(seg)
        total += float(dur)
        if kind == last_kind:
            kind_run += 1
        else:
            kind_run = 1
        last_kind = kind
        last_path = str(path)
        slide_run = slide_run + 1 if kind == "slide" else 0
        image_run = image_run + 1 if kind == "image" else 0
        video_run = video_run + 1 if kind == "video" else 0

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
