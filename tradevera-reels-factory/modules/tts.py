from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

from .utils import run_cmd, which_any


def _find_piper_model(project_root: Path) -> Path | None:
    env_model = os.environ.get("PIPER_MODEL")
    if env_model:
        p = Path(env_model).expanduser()
        if p.exists():
            return p
    search_roots = [project_root / "assets" / "tts", project_root / "assets" / "brand", project_root]
    for root in search_roots:
        if not root.exists():
            continue
        for p in root.rglob("*.onnx"):
            return p
    return None


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _espeak_text(text: str) -> str:
    # eSpeak sounds better with commas/periods than repeated ellipsis pause markers.
    text = text.replace("...", ", ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def synthesize_voice(text: str, out_wav: Path, project_root: Path, logger: Any = None) -> dict[str, str]:
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    piper = which_any("piper", "piper.exe")
    espeak = which_any("espeak-ng", "espeak")
    require_piper = _env_truthy("TV_REQUIRE_PIPER")

    if piper:
        model = _find_piper_model(project_root)
        if model:
            if logger:
                logger.step(f"TTS engine: Piper ({Path(piper).name}) with model {model.name}")
            cp = subprocess.run(
                [piper, "--model", str(model), "--output_file", str(out_wav)],
                input=text,
                text=True,
                capture_output=True,
            )
            if cp.returncode == 0 and out_wav.exists() and out_wav.stat().st_size > 0:
                return {"engine": "piper", "model": model.name}
            if logger:
                logger.warn("Piper synthesis failed; falling back to eSpeak NG if available")
                if cp.stderr:
                    logger.step("Piper stderr: " + cp.stderr.strip()[:1200])
        elif logger:
            logger.warn("Piper found but no .onnx model found (set PIPER_MODEL or add one under assets/tts)")

    if require_piper:
        raise RuntimeError(
            "TV_REQUIRE_PIPER=1 is set and Piper synthesis is unavailable. Install Piper + model (or unset TV_REQUIRE_PIPER)."
        )

    if espeak:
        if logger:
            logger.warn("Using eSpeak NG fallback for TTS (lower voice quality than Piper)")
            logger.step(f"TTS engine: {Path(espeak).name}")
        espeak_voice = os.environ.get("TV_ESPEAK_VOICE", "en-us")
        espeak_speed = os.environ.get("TV_ESPEAK_SPEED", "148")
        espeak_pitch = os.environ.get("TV_ESPEAK_PITCH", "40")
        espeak_gap = os.environ.get("TV_ESPEAK_GAP", "6")
        cmd = [
            espeak,
            "-w",
            str(out_wav),
            "-s",
            espeak_speed,
            "-p",
            espeak_pitch,
            "-g",
            espeak_gap,
            "-v",
            espeak_voice,
            _espeak_text(text),
        ]
        run_cmd(cmd, logger=logger)
        if out_wav.exists() and out_wav.stat().st_size > 0:
            return {"engine": Path(espeak).name, "model": "builtin"}

    raise RuntimeError(
        "No local TTS engine available. Install Piper (+ model) or eSpeak NG. See README and tools/setup_check.py"
    )
