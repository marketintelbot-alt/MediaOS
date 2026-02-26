from __future__ import annotations

import os
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


def _synthetic_sfx_lavfi(event_type: str) -> tuple[str, float]:
    et = (event_type or "").lower()
    if et == "hook_hit":
        return ("sine=frequency=960:sample_rate=48000", 0.16)
    if et == "cta":
        return ("sine=frequency=620:sample_rate=48000", 0.22)
    return ("anoisesrc=color=white:sample_rate=48000", 0.28)


def _env_truthy(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


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
    allow_synthetic_fallbacks = _env_truthy("TV_SYNTHETIC_AUDIO_FALLBACKS", default=True)

    output_wav.parent.mkdir(parents=True, exist_ok=True)

    cmd: list[str] = [ffmpeg, "-y", "-i", str(voice_wav)]
    music_mode = "file" if music_path else ("synthetic" if allow_synthetic_fallbacks else "none")
    sfx_mode = "file" if sfx_pool else ("synthetic" if allow_synthetic_fallbacks else "none")
    sfx_file_inputs: list[tuple[Path, dict[str, Any]]] = []
    sfx_synth_inputs: list[tuple[str, float, dict[str, Any]]] = []

    if music_mode == "file":
        cmd += ["-stream_loop", "-1", "-i", str(music_path)]
    elif music_mode == "synthetic":
        cmd += ["-f", "lavfi", "-t", str(target_length), "-i", "anoisesrc=color=violet:sample_rate=48000"]
        cmd += ["-f", "lavfi", "-t", str(target_length), "-i", "sine=frequency=96:sample_rate=48000"]

    for idx, ev in enumerate(sfx_events):
        if sfx_mode == "file" and sfx_pool:
            sfx_file_inputs.append((sfx_pool[idx % len(sfx_pool)], ev))
            cmd += ["-i", str(sfx_file_inputs[-1][0])]
        elif sfx_mode == "synthetic":
            lavfi, dur = _synthetic_sfx_lavfi(str(ev.get("type", "")))
            sfx_synth_inputs.append((lavfi, dur, ev))
            cmd += ["-f", "lavfi", "-t", f"{dur:.3f}", "-i", lavfi]

    filter_parts: list[str] = []
    mix_inputs: list[str] = []

    voice_gain = "volume=-2dB," if safe_mode else ""
    filter_parts.append(f"[0:a]{voice_gain}{_voice_chain()}[v]")

    input_index = 1
    if music_mode == "file" and music_path:
        music_gain = 0.13 if safe_mode else 0.18
        filter_parts.append(
            f"[{input_index}:a]atrim=0:{target_length},asetpts=N/SR/TB,volume={music_gain}[m0]"
        )
        filter_parts.append(
            "[m0][v]sidechaincompress=threshold=0.04:ratio=10:attack=12:release=260[md]"
        )
        mix_inputs.append("[md]")
        input_index += 1
    elif music_mode == "synthetic":
        # Two-layer ambient pad to avoid dead voice-only output when no assets exist.
        filter_parts.append(
            f"[{input_index}:a]highpass=f=180,lowpass=f=4800,volume=0.018,afade=t=in:st=0:d=0.6,afade=t=out:st={max(0.1,target_length-0.8):.2f}:d=0.8[nbed]"
        )
        filter_parts.append(
            f"[{input_index+1}:a]lowpass=f=180,highpass=f=55,volume=0.020,afade=t=in:st=0:d=0.6,afade=t=out:st={max(0.1,target_length-0.8):.2f}:d=0.8[sbed]"
        )
        filter_parts.append("[nbed][sbed]amix=inputs=2:normalize=0[m0]")
        filter_parts.append("[m0][v]sidechaincompress=threshold=0.035:ratio=12:attack=10:release=280[md]")
        mix_inputs.append("[md]")
        input_index += 2
    else:
        mix_inputs.append("[v]")

    all_sfx_events: list[tuple[dict[str, Any], str]] = []
    if sfx_file_inputs:
        all_sfx_events.extend((ev, "file") for _, ev in sfx_file_inputs)
    if sfx_synth_inputs:
        all_sfx_events.extend((ev, "synthetic") for _, _, ev in sfx_synth_inputs)

    for sfx_idx, (ev, source_kind) in enumerate(all_sfx_events):
        delay_ms = max(0, int(float(ev.get("time", 0.0)) * 1000))
        label = f"s{sfx_idx}"
        ev_type = str(ev.get("type", "")).lower()
        if source_kind == "synthetic":
            if ev_type == "hook_hit":
                sfx_filter = "highpass=f=480,lowpass=f=4200,afade=t=in:st=0:d=0.01,afade=t=out:st=0.08:d=0.08,volume=0.050"
            elif ev_type == "cta":
                sfx_filter = "aecho=0.8:0.88:18:0.18,lowpass=f=3200,afade=t=in:st=0:d=0.01,afade=t=out:st=0.12:d=0.10,volume=0.045"
            else:
                sfx_filter = "highpass=f=2500,lowpass=f=9000,afade=t=in:st=0:d=0.01,afade=t=out:st=0.14:d=0.12,volume=0.030"
            filter_parts.append(
                f"[{input_index + sfx_idx}:a]{sfx_filter},adelay={delay_ms}|{delay_ms}[{label}]"
            )
        else:
            # subtle premium SFX level; short trim prevents clutter.
            filter_parts.append(
                f"[{input_index + sfx_idx}:a]atrim=0:0.8,afade=t=in:st=0:d=0.02,afade=t=out:st=0.55:d=0.2,volume=0.10,adelay={delay_ms}|{delay_ms}[{label}]"
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
        if music_mode == "file" and music_path:
            logger.step(f"Music bed: {music_path.name}")
        elif music_mode == "synthetic":
            logger.warn("No local music found in assets/music; using synthetic ambient bed fallback")
        else:
            logger.warn("No local music found in assets/music; rendering voice-only mix")
        sfx_count = len(all_sfx_events)
        if sfx_count:
            logger.step(f"SFX overlays: {sfx_count} event(s) ({sfx_mode})")
        elif sfx_pool:
            logger.step("SFX library present but no events applied")
        elif sfx_mode == "synthetic" and sfx_events:
            logger.step("SFX events requested but synthetic generation skipped")
        else:
            logger.step("No local SFX found in assets/sfx")

    return {
        "music": str(music_path) if music_path else None,
        "music_mode": music_mode,
        "sfx_mode": sfx_mode,
        "sfx_count": len(all_sfx_events),
        "safe_mode": safe_mode,
    }
