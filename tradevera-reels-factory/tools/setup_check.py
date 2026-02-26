#!/usr/bin/env python3
from __future__ import annotations

import importlib
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _which_path(name: str) -> str | None:
    if name in {"ffmpeg", "ffprobe"}:
        for p in (Path("/opt/homebrew/opt/ffmpeg-full/bin") / name, Path("/usr/local/opt/ffmpeg-full/bin") / name):
            if p.exists():
                return str(p)
    home = Path.home()
    for base in (home / ".local" / "bin", home / "Library" / "Python"):
        if not base.is_dir():
            continue
        if base.name == "Python":
            for py_ver in sorted(base.iterdir(), reverse=True):
                p = py_ver / "bin" / name
                if p.exists():
                    return str(p)
        else:
            p = base / name
            if p.exists():
                return str(p)
    return shutil.which(name)


def check_bin(name: str) -> bool:
    return _which_path(name) is not None


def ffmpeg_caption_filters_ok() -> bool | None:
    ffmpeg = _which_path("ffmpeg")
    if not ffmpeg:
        return None
    cp = subprocess.run([ffmpeg, "-hide_banner", "-filters"], text=True, capture_output=True)
    text = (cp.stdout or "") + "\n" + (cp.stderr or "")
    return (" subtitles " in text) or (" drawtext " in text)


def piper_usable() -> bool:
    piper = _which_path("piper")
    if not piper:
        return False
    cp = subprocess.run([piper, "--help"], text=True, capture_output=True)
    return cp.returncode == 0


def main() -> int:
    system = platform.system().lower()
    print("tradevera-reels-factory setup check")
    print(f"Python: {sys.version.split()[0]}")
    print(f"OS: {platform.system()} {platform.release()}")
    print("")

    checks = []
    checks.append(("ffmpeg", check_bin("ffmpeg")))
    checks.append(("ffprobe", check_bin("ffprobe")))
    checks.append(("piper", piper_usable()))
    checks.append(("espeak-ng / espeak", check_bin("espeak-ng") or check_bin("espeak")))

    try:
        importlib.import_module("PIL")
        pillow_ok = True
    except Exception:
        pillow_ok = False
    checks.append(("Pillow (python)", pillow_ok))

    try:
        importlib.import_module("whisper")
        whisper_ok = True
    except Exception:
        whisper_ok = False
    checks.append(("Whisper (optional)", whisper_ok))

    for name, ok in checks:
        print(f"[{ 'OK' if ok else 'MISSING' }] {name}")
    caption_filters = ffmpeg_caption_filters_ok()
    if caption_filters is True:
        print("[OK] FFmpeg caption burn filters (subtitles/drawtext)")
    elif caption_filters is False:
        print("[WARN] FFmpeg caption burn filters missing (install ffmpeg-full or build FFmpeg with libass/freetype)")

    print("")
    print("Actionable fixes:")
    if system == "darwin":
        print("- FFmpeg: brew install ffmpeg")
        print("- eSpeak NG fallback: brew install espeak")
        print("- Piper: pip install --user piper-tts pathvalidate (or install binary) + add a free .onnx voice model under assets/tts")
    elif system == "windows":
        print("- FFmpeg: install the free static build and add ffmpeg/bin to PATH")
        print("- eSpeak NG fallback: install eSpeak NG and add it to PATH")
        print("- Piper: install the free Piper binary and a free .onnx voice model, then set PIPER_MODEL")
    else:
        print("- FFmpeg: sudo apt install ffmpeg (or distro equivalent)")
        print("- eSpeak NG fallback: sudo apt install espeak-ng")
        print("- Piper: install the free Piper binary and a free .onnx voice model, then set PIPER_MODEL")
    print("- Python deps: pip install -r requirements.txt")
    print("- Optional better captions: pip install openai-whisper (heavy) and pre-download a local model")
    print("")
    print("Core stack is completely free. No API keys are required for reel generation.")

    # Fail only if mandatory pieces are missing.
    ffmpeg_ok = check_bin("ffmpeg") and check_bin("ffprobe")
    tts_ok = check_bin("piper") or check_bin("espeak-ng") or check_bin("espeak")
    return 0 if (ffmpeg_ok and tts_ok and pillow_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
