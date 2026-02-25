from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .utils import VIDEO_EXTS, ffprobe_json, list_media_files


DEFAULT_KEYWORDS = {
    "chart": ["chart", "screen", "terminal", "dashboard"],
    "market": ["market", "city", "exchange", "trading_floor"],
    "keyboard": ["keyboard", "desk", "hands", "typing"],
    "abstract": ["abstract", "grid", "data", "numbers"],
}


def scan_broll_library(broll_dir: Path) -> list[dict[str, Any]]:
    clips: list[dict[str, Any]] = []
    tags_manifest = broll_dir / "tags.json"
    tags = {}
    if tags_manifest.exists():
        try:
            tags = json.loads(tags_manifest.read_text(encoding="utf-8"))
        except Exception:
            tags = {}
    for path in list_media_files(broll_dir, VIDEO_EXTS):
        meta: dict[str, Any] = {"path": path, "tags": [], "duration": None, "width": None, "height": None}
        tag_item = tags.get(path.name, {}) if isinstance(tags, dict) else {}
        if isinstance(tag_item, dict):
            meta["tags"] = list(tag_item.get("tags") or [])
        else:
            meta["tags"] = []
        if not meta["tags"]:
            meta["tags"] = infer_tags_from_name(path.name)
        try:
            info = ffprobe_json(path)
            for s in info.get("streams", []):
                if s.get("codec_type") == "video":
                    meta["width"] = s.get("width")
                    meta["height"] = s.get("height")
                    break
            meta["duration"] = float((info.get("format") or {}).get("duration") or 0)
        except Exception:
            pass
        clips.append(meta)
    return clips


def infer_tags_from_name(name: str) -> list[str]:
    base = re.sub(r"[^a-z0-9]+", " ", name.lower())
    out: list[str] = []
    for bucket, keys in DEFAULT_KEYWORDS.items():
        if any(k in base for k in keys):
            out.append(bucket)
    if not out:
        out = ["abstract"]
    return out


def select_broll(clips: list[dict[str, Any]], idea: str, max_items: int = 8, no_broll: bool = False) -> list[dict[str, Any]]:
    if no_broll or not clips:
        return []
    idea_lower = idea.lower()
    scored: list[tuple[int, dict[str, Any]]] = []
    for clip in clips:
        score = 0
        tags = [str(t).lower() for t in (clip.get("tags") or [])]
        if any(k in idea_lower for k in ["risk", "equity", "drawdown", "stop"]):
            score += 3 if ("chart" in tags or "abstract" in tags) else 0
        if "setup" in idea_lower or "noise" in idea_lower:
            score += 2 if ("screen" in tags or "chart" in tags) else 0
        if clip.get("duration") and float(clip["duration"]) > 2.0:
            score += 1
        score += len(tags)
        scored.append((score, clip))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:max_items]]


def tag_broll_directory(broll_dir: Path) -> dict[str, Any]:
    manifest: dict[str, Any] = {}
    for clip in scan_broll_library(broll_dir):
        p = Path(clip["path"])
        manifest[p.name] = {
            "tags": clip.get("tags") or [],
            "duration": clip.get("duration"),
            "width": clip.get("width"),
            "height": clip.get("height"),
        }
    (broll_dir / "tags.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
