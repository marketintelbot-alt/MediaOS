from __future__ import annotations

import glob
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

VIDEO_W = 1080
VIDEO_H = 1920
FPS = 30
SAFE_MARGIN_X = 72
SAFE_MARGIN_Y = 120

DEFAULT_PALETTE = {
    "background": "#070A0F",
    "surface": "#0D1220",
    "text_primary": "#E8EEF6",
    "text_secondary": "#9AA7B8",
    "accent": "#22D3EE",
}

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".ogg"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}


def timestamp_slug() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def choose_length(user_length: int | None) -> int:
    if user_length is None:
        return random.randint(22, 30)
    if not 20 <= user_length <= 35:
        raise ValueError("--length must be between 20 and 35 seconds")
    return int(user_length)


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def load_palette(brand_dir: Path) -> dict[str, str]:
    palette_path = brand_dir / "palette.json"
    if not palette_path.exists():
        write_json(palette_path, DEFAULT_PALETTE)
        return dict(DEFAULT_PALETTE)
    try:
        raw = json.loads(palette_path.read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    palette = dict(DEFAULT_PALETTE)
    for k, v in raw.items() if isinstance(raw, dict) else []:
        if isinstance(v, str) and v.startswith("#"):
            palette[k] = v
    return palette


def run_cmd(
    cmd: Sequence[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    capture_output: bool = True,
    logger: "BuildLogger | None" = None,
) -> subprocess.CompletedProcess[str]:
    if logger is not None:
        logger.step("RUN: " + " ".join(_shorten(str(c)) for c in cmd))
    cp = subprocess.run(
        list(cmd),
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=capture_output,
    )
    if check and cp.returncode != 0:
        if logger is not None:
            logger.warn(f"Command failed ({cp.returncode}): {' '.join(_shorten(str(c)) for c in cmd)}")
            if cp.stderr:
                logger.step("stderr: " + cp.stderr.strip()[:1500])
        raise RuntimeError(cp.stderr.strip() or cp.stdout.strip() or f"Command failed: {cmd}")
    return cp


def _shorten(s: str, n: int = 120) -> str:
    return s if len(s) <= n else s[: n - 3] + "..."


def which_any(*names: str) -> str | None:
    for name in names:
        if name in {"ffmpeg", "ffprobe"}:
            for alt in ("/opt/homebrew/opt/ffmpeg-full/bin", "/usr/local/opt/ffmpeg-full/bin"):
                candidate = Path(alt) / name
                if candidate.exists():
                    return str(candidate)
        path = shutil.which(name)
        if path:
            return path
    return None


def ffprobe_json(path: Path) -> dict[str, Any]:
    ffprobe = which_any("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe not found")
    cp = run_cmd(
        [ffprobe, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
        check=True,
    )
    return json.loads(cp.stdout or "{}")


def media_duration(path: Path) -> float:
    info = ffprobe_json(path)
    fmt = info.get("format") or {}
    try:
        return float(fmt.get("duration") or 0.0)
    except Exception:
        return 0.0


def video_stream_info(path: Path) -> dict[str, Any]:
    info = ffprobe_json(path)
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "video":
            return stream
    return {}


def has_audio_stream(path: Path) -> bool:
    info = ffprobe_json(path)
    return any(s.get("codec_type") == "audio" for s in info.get("streams", []))


def ffmpeg_version() -> str:
    ffmpeg = which_any("ffmpeg")
    if not ffmpeg:
        return "missing"
    try:
        cp = run_cmd([ffmpeg, "-version"], check=False)
        line = (cp.stdout or "").splitlines()[0] if cp.stdout else "ffmpeg present"
        return line.strip()
    except Exception:
        return "ffmpeg present"


def parse_image_inputs(patterns: list[str] | None) -> list[Path]:
    if not patterns:
        return []
    out: list[Path] = []
    seen: set[str] = set()
    for pattern in patterns:
        matches = glob.glob(pattern)
        if not matches:
            matches = [pattern]
        for m in matches:
            p = Path(m).expanduser().resolve()
            if not p.exists() or p.suffix.lower() not in IMAGE_EXTS:
                continue
            key = str(p)
            if key in seen:
                continue
            seen.add(key)
            out.append(p)
    return out[:12]


def list_media_files(dir_path: Path, exts: set[str]) -> list[Path]:
    if not dir_path.exists():
        return []
    return sorted([p for p in dir_path.iterdir() if p.is_file() and p.suffix.lower() in exts])


def seconds_to_ass(t: float) -> str:
    if t < 0:
        t = 0.0
    hours = int(t // 3600)
    minutes = int((t % 3600) // 60)
    seconds = t % 60
    return f"{hours}:{minutes:02d}:{seconds:05.2f}"


def ass_color(hex_color: str) -> str:
    c = hex_color.strip().lstrip("#")
    if len(c) != 6:
        c = DEFAULT_PALETTE["text_primary"].lstrip("#")
    r = int(c[0:2], 16)
    g = int(c[2:4], 16)
    b = int(c[4:6], 16)
    return f"&H{b:02X}{g:02X}{r:02X}&"


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9%+/-]+(?:'[A-Za-z]+)?", text)


def wrap_text_words(text: str, max_chars: int = 28) -> list[str]:
    chunks: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for w in text.split():
        add = len(w) + (1 if cur else 0)
        if cur and cur_len + add > max_chars:
            chunks.append(" ".join(cur))
            cur = [w]
            cur_len = len(w)
        else:
            cur.append(w)
            cur_len += add
    if cur:
        chunks.append(" ".join(cur))
    return chunks or [text]


def split_caption_chunks(text: str, max_words: int = 7) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    sentence_parts = re.split(r"(?<=[.!?;:])\s+", text)
    out: list[str] = []
    for part in sentence_parts:
        part = part.strip()
        if not part:
            continue
        ws = part.split()
        if len(ws) <= max_words:
            out.append(part)
            continue
        for i in range(0, len(ws), max_words):
            out.append(" ".join(ws[i : i + max_words]))
    return out


def pick_keywords(text: str, max_count: int = 2) -> list[str]:
    stop = {
        "the",
        "and",
        "for",
        "with",
        "this",
        "that",
        "your",
        "you",
        "from",
        "into",
        "most",
        "traders",
        "trade",
        "daily",
        "follow",
        "tradevera",
    }
    candidates = [w for w in words(text) if len(w) > 3 and w.lower() not in stop]
    uniq: list[str] = []
    for w in candidates:
        if w.lower() not in {u.lower() for u in uniq}:
            uniq.append(w)
    return uniq[:max_count]


def sanitize_title(text: str, max_len: int = 90) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len].strip()


def seed_from_text(text: str) -> int:
    return abs(hash(text)) % (2**31)


def ffmpeg_filter_escape(path: Path | str) -> str:
    s = str(path)
    s = s.replace("\\", "\\\\")
    s = s.replace(":", "\\:")
    s = s.replace("'", "\\'")
    s = s.replace(",", "\\,")
    s = s.replace(" ", "\\ ")
    return s


def concat_list_escape(path: Path | str) -> str:
    s = str(path)
    return s.replace("'", "'\\''")


def basic_peak_check(video_path: Path, logger: "BuildLogger | None" = None) -> tuple[bool, float | None]:
    ffmpeg = which_any("ffmpeg")
    if not ffmpeg:
        return False, None
    cp = run_cmd(
        [ffmpeg, "-hide_banner", "-i", str(video_path), "-af", "volumedetect", "-f", "null", "-"],
        check=False,
        logger=logger,
    )
    text = (cp.stderr or "") + "\n" + (cp.stdout or "")
    m = re.search(r"max_volume:\s*(-?\d+(?:\.\d+)?) dB", text)
    if not m:
        return False, None
    peak = float(m.group(1))
    return peak <= -0.3, peak


@dataclass
class BuildLogger:
    lines: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def _stamp(self) -> str:
        return time.strftime("%H:%M:%S")

    def step(self, message: str) -> None:
        self.lines.append(f"[{self._stamp()}] {message}")

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        self.lines.append(f"[{self._stamp()}] WARNING: {message}")

    def add_versions(self) -> None:
        self.step(f"python: {sys.version.split()[0]}")
        self.step(f"ffmpeg: {ffmpeg_version()}")

    def write(self, path: Path) -> None:
        write_text(path, "\n".join(self.lines).strip() + "\n")
