#!/usr/bin/env python3
from __future__ import annotations

import importlib
import platform
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check_bin(name: str) -> bool:
    if name in {"ffmpeg", "ffprobe"}:
        for p in (Path("/opt/homebrew/opt/ffmpeg-full/bin") / name, Path("/usr/local/opt/ffmpeg-full/bin") / name):
            if p.exists():
                return True
    return shutil.which(name) is not None


def main() -> int:
    system = platform.system().lower()
    print("tradevera-reels-factory setup check")
    print(f"Python: {sys.version.split()[0]}")
    print(f"OS: {platform.system()} {platform.release()}")
    print("")

    checks = []
    checks.append(("ffmpeg", check_bin("ffmpeg")))
    checks.append(("ffprobe", check_bin("ffprobe")))
    checks.append(("piper", check_bin("piper")))
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

    print("")
    print("Actionable fixes:")
    if system == "darwin":
        print("- FFmpeg: brew install ffmpeg")
        print("- eSpeak NG fallback: brew install espeak")
        print("- Piper: install the free Piper binary and a free .onnx voice model, then set PIPER_MODEL=/path/model.onnx")
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
