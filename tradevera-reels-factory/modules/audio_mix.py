from __future__ import annotations

import random
from pathlib import Path
from typing import Any

from .utils import AUDIO_EXTS, list_media_files, run_cmd, which_any


def _voice_chain() -> str:
    # Approximate studio chain with only common FFmpeg filters.
    return (
        "highpass=f=70,"
        "afftdn=nf=-25,"
        "acompressor=threshold=0.08:ratio=3:attack=5:release=120:makeup=2,"
        "equalizer=f=250:t=q:w=1:g=-2,"
        "equalizer=f=3200:t=q:w=1:g=2,"
        "equalizer=f=6500:t=q:w=1:g=-2.5,"
        "alimiter=limit=0.95"
    )


def choose_music_and_sfx(project_root: Path) -> dict[str, list[Path] | Path | None]:
    music_files = list_media_files(project_root / "assets" / "music", AUDIO_EXTS)
    sfx_files = list_media_files(project_root / "assets" / "sfx", AUDIO_EXTS)
    return {
        "music": random.choice(music_files) if music_files else None,
        "sfx": sfx_files,
    }


def mix_audio(
    voice_wav: Path,
    output_wav: Path,
    target_length: int,
    project_root: Path,
    sfx_events: list[dict[str, Any]] | None,
    logger: Any = None,
    safe_mode: bool = False,
) -> dict[str, Any]:
    ffmpeg = which_any("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found")

    picks = choose_music_and_sfx(project_root)
    music_path = picks.get("music")
    sfx_pool: list[Path] = list(picks.get("sfx") or [])
    sfx_events = sfx_events or []

    output_wav.parent.mkdir(parents=True, exist_ok=True)

    cmd: list[str] = [ffmpeg, "-y", "-i", str(voice_wav)]
    if music_path:
        cmd += ["-stream_loop", "-1", "-i", str(music_path)]
    sfx_inputs: list[tuple[Path, dict[str, Any]]] = []
    for idx, ev in enumerate(sfx_events):
        if not sfx_pool:
            break
        sfx_inputs.append((sfx_pool[idx % len(sfx_pool)], ev))
        cmd += ["-i", str(sfx_inputs[-1][0])]

    filter_parts: list[str] = []
    mix_inputs: list[str] = []

    voice_gain = "volume=-2dB," if safe_mode else ""
    filter_parts.append(f"[0:a]{voice_gain}{_voice_chain()}[v]")
    mix_inputs.append("[v]")

    input_index = 1
    if music_path:
        music_gain = 0.13 if safe_mode else 0.18
        filter_parts.append(
            f"[{input_index}:a]atrim=0:{target_length},asetpts=N/SR/TB,volume={music_gain}[m0]"
        )
        filter_parts.append(
            "[m0][v]sidechaincompress=threshold=0.04:ratio=10:attack=12:release=260[md]"
        )
        mix_inputs.append("[md]")
        input_index += 1

    for sfx_idx, (_path, ev) in enumerate(sfx_inputs):
        delay_ms = max(0, int(float(ev.get("time", 0.0)) * 1000))
        label = f"s{sfx_idx}"
        # subtle premium SFX level; short trim prevents clutter.
        filter_parts.append(
            f"[{input_index + sfx_idx}:a]atrim=0:0.8,afade=t=in:st=0:d=0.02,afade=t=out:st=0.55:d=0.2,volume=0.12,adelay={delay_ms}|{delay_ms}[{label}]"
        )
        mix_inputs.append(f"[{label}]")

    if len(mix_inputs) == 1:
        filter_parts.append(f"[v]apad=pad_dur={target_length},loudnorm=I=-15:TP=-1.5:LRA=7[mix]")
    else:
        amix_inputs = "".join(mix_inputs)
        filter_parts.append(f"{amix_inputs}amix=inputs={len(mix_inputs)}:normalize=0[pre]")
        filter_parts.append(
            f"[pre]alimiter=limit=0.95,apad=pad_dur={target_length},loudnorm=I=-15:TP=-1.5:LRA=7[mix]"
        )

    cmd += [
        "-filter_complex",
        ";".join(filter_parts),
        "-map",
        "[mix]",
        "-t",
        str(target_length),
        "-ar",
        "48000",
        "-ac",
        "2",
        "-c:a",
        "pcm_s16le",
        str(output_wav),
    ]
    run_cmd(cmd, logger=logger)

    if logger:
        if music_path:
            logger.step(f"Music bed: {music_path.name}")
        else:
            logger.warn("No local music found in assets/music; rendering voice-only mix")
        if sfx_inputs:
            logger.step(f"SFX overlays: {len(sfx_inputs)} event(s)")
        elif sfx_pool:
            logger.step("SFX library present but no events applied")
        else:
            logger.step("No local SFX found in assets/sfx")

    return {
        "music": str(music_path) if music_path else None,
        "sfx_count": len(sfx_inputs),
        "safe_mode": safe_mode,
    }
