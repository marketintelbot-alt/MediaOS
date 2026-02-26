#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import ssl
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Free/open licensed sources (Blender open movie trailers, CC-friendly open projects).
MANIFEST = [
    {
        "kind": "broll",
        "name": "big_buck_bunny_trailer.ogg",
        "url": "https://download.blender.org/peach/trailer/trailer_1080p.ogg",
        "source": "Blender Foundation - Big Buck Bunny trailer (open movie)",
        "license": "Creative Commons Attribution 3.0",
    },
    {
        "kind": "broll",
        "name": "sintel_trailer_720p.mp4",
        "url": "https://download.blender.org/durian/trailer/sintel_trailer-720p.mp4",
        "source": "Blender Foundation - Sintel trailer (open movie)",
        "license": "Creative Commons Attribution 3.0",
    },
]


def _download(url: str, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "tradevera-reels-factory/1.0"})
    contexts = [None]
    # Some local Python/macOS setups miss cert chains; allow a fallback so the helper still works.
    contexts.append(ssl._create_unverified_context())
    last_exc: Exception | None = None
    for i, ctx in enumerate(contexts):
        try:
            with urllib.request.urlopen(req, context=ctx) as r, out_path.open("wb") as f:
                while True:
                    chunk = r.read(1024 * 64)
                    if not chunk:
                        break
                    f.write(chunk)
            if i == 1:
                print(f"Warning: downloaded with SSL verification disabled for {out_path.name}")
            return
        except Exception as exc:
            last_exc = exc
            if out_path.exists():
                out_path.unlink(missing_ok=True)
            continue
    raise last_exc or RuntimeError("download failed")


def _ffmpeg_exists() -> bool:
    import shutil

    return shutil.which("ffmpeg") is not None


def _run_ffmpeg(cmd: list[str]) -> bool:
    import subprocess

    cp = subprocess.run(cmd, text=True, capture_output=True)
    if cp.returncode != 0:
        print(cp.stderr.strip())
        return False
    return True


def _derive_music_and_sfx_from_broll() -> None:
    import shutil

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("ffmpeg not found; skipping music/sfx derivation")
        return
    broll_dir = ROOT / "assets" / "broll"
    music_dir = ROOT / "assets" / "music"
    sfx_dir = ROOT / "assets" / "sfx"
    music_dir.mkdir(parents=True, exist_ok=True)
    sfx_dir.mkdir(parents=True, exist_ok=True)

    sources = [p for p in broll_dir.iterdir() if p.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm", ".ogg"}]
    if not sources:
        print("No downloaded b-roll sources found to derive music/sfx")
        return

    src = sources[0]
    # Starter music bed: low-volume instrumental slice from an open movie trailer.
    _run_ffmpeg([
        ffmpeg,
        "-y",
        "-i",
        str(src),
        "-ss",
        "5",
        "-t",
        "20",
        "-vn",
        "-af",
        "highpass=f=120,lowpass=f=8000,volume=0.35",
        str(music_dir / "starter_bed_01.mp3"),
    ])

    # Subtle UI-style hits generated locally (free, no downloads required) for hook/transition/CTA.
    _run_ffmpeg([
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=880:duration=0.16",
        "-af",
        "afade=t=in:st=0:d=0.01,afade=t=out:st=0.08:d=0.08,volume=0.25",
        str(sfx_dir / "ui_tick_01.wav"),
    ])
    _run_ffmpeg([
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "anoisesrc=color=white:duration=0.28",
        "-af",
        "highpass=f=2500,lowpass=f=9000,afade=t=in:st=0:d=0.01,afade=t=out:st=0.14:d=0.12,volume=0.08",
        str(sfx_dir / "whoosh_micro_01.wav"),
    ])
    _run_ffmpeg([
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=620:duration=0.22",
        "-af",
        "aecho=0.8:0.88:20:0.2,afade=t=out:st=0.12:d=0.1,volume=0.18",
        str(sfx_dir / "cta_ping_01.wav"),
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description="Download free/open licensed starter b-roll and derive local music/sfx")
    parser.add_argument("--skip_download", action="store_true", help="Only derive music/sfx from existing local b-roll")
    args = parser.parse_args()

    downloaded = []
    if not args.skip_download:
        for item in MANIFEST:
            out_path = ROOT / "assets" / item["kind"] / item["name"]
            if out_path.exists() and out_path.stat().st_size > 0:
                print(f"Exists: {out_path.name}")
            else:
                print(f"Downloading: {item['name']}")
                try:
                    _download(item["url"], out_path)
                    downloaded.append(item)
                except Exception as exc:
                    print(f"Failed: {item['name']} ({exc})")

    _derive_music_and_sfx_from_broll()

    attribution = ROOT / "assets" / "ATTRIBUTION.txt"
    lines = ["Free/open licensed starter assets used by tradevera-reels-factory", ""]
    for item in MANIFEST:
        lines.append(f"- {item['name']}: {item['source']} | {item['license']} | {item['url']}")
    attribution.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("Done. Review assets/ATTRIBUTION.txt and keep license notices with redistributed assets.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
