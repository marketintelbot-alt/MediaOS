from __future__ import annotations

import os
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


def synthesize_voice(text: str, out_wav: Path, project_root: Path, logger: Any = None) -> dict[str, str]:
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    piper = which_any("piper", "piper.exe")
    espeak = which_any("espeak-ng", "espeak")

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

    if espeak:
        if logger:
            logger.warn("Using eSpeak NG fallback for TTS (lower voice quality than Piper)")
            logger.step(f"TTS engine: {Path(espeak).name}")
        cmd = [espeak, "-w", str(out_wav), "-s", "155", "-v", "en-us", text]
        run_cmd(cmd, logger=logger)
        if out_wav.exists() and out_wav.stat().st_size > 0:
            return {"engine": Path(espeak).name, "model": "builtin"}

    raise RuntimeError(
        "No local TTS engine available. Install Piper (+ model) or eSpeak NG. See README and tools/setup_check.py"
    )
