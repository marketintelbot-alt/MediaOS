from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path
from typing import Any

from .utils import ass_color, media_duration, pick_keywords, seconds_to_ass, split_caption_chunks


def _sanitize_ass_text(text: str) -> str:
    text = text.replace("{", "(").replace("}", ")")
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _highlight_keywords(text: str, accent_hex: str, base_hex: str) -> str:
    accent = ass_color(accent_hex)
    base = ass_color(base_hex)
    out = text
    for kw in pick_keywords(text, max_count=2):
        pattern = re.compile(rf"\b({re.escape(kw)})\b", re.IGNORECASE)
        def repl(m: re.Match[str]) -> str:
            return "{\\c" + accent + "}" + m.group(1) + "{\\c" + base + "}"
        out, n = pattern.subn(repl, out, count=1)
        if n == 0:
            continue
    return out


def _chunks_from_phrase_fallback(narration_text: str, audio_dur: float) -> list[dict[str, Any]]:
    pieces = split_caption_chunks(narration_text, max_words=7)
    if not pieces:
        return []
    weights = [max(1, len(p.split())) for p in pieces]
    total_w = sum(weights) or 1
    cur = 0.0
    out: list[dict[str, Any]] = []
    # leave a tiny tail room to avoid overshooting exact duration
    usable = max(0.5, audio_dur - 0.1)
    for i, piece in enumerate(pieces):
        dur = usable * (weights[i] / total_w)
        dur = max(0.38, dur)
        start = cur
        end = min(audio_dur, start + dur)
        out.append({"start": round(start, 3), "end": round(end, 3), "text": piece})
        cur = end
    if out:
        out[-1]["end"] = round(max(out[-1]["end"], audio_dur - 0.01), 3)
    return out


def _chunks_from_whisper(voice_wav: Path, logger: Any = None) -> list[dict[str, Any]] | None:
    try:
        import whisper  # type: ignore
    except Exception:
        return None

    model_name = os.environ.get("TV_WHISPER_MODEL", "tiny")
    try:
        if logger:
            logger.step(f"Caption timing: attempting local Whisper ({model_name}) word timestamps")
        model = whisper.load_model(model_name)
        result = model.transcribe(str(voice_wav), word_timestamps=True, verbose=False)
        raw_words: list[dict[str, Any]] = []
        for seg in result.get("segments", []):
            for w in seg.get("words", []) or []:
                word_text = str(w.get("word", "")).strip()
                if not word_text:
                    continue
                raw_words.append(
                    {
                        "text": word_text,
                        "start": float(w.get("start") or seg.get("start") or 0.0),
                        "end": float(w.get("end") or seg.get("end") or 0.0),
                    }
                )
        if not raw_words:
            return None

        chunks: list[dict[str, Any]] = []
        bucket: list[dict[str, Any]] = []
        for item in raw_words:
            if bucket and (
                len(bucket) >= 7 or item["start"] - bucket[-1]["end"] > 0.32 or item["text"].endswith((".", "!", "?", ";"))
            ):
                chunks.append(
                    {
                        "start": bucket[0]["start"],
                        "end": max(bucket[-1]["end"], bucket[0]["start"] + 0.25),
                        "text": " ".join(w["text"] for w in bucket).strip(),
                    }
                )
                bucket = []
            bucket.append(item)
        if bucket:
            chunks.append(
                {
                    "start": bucket[0]["start"],
                    "end": max(bucket[-1]["end"], bucket[0]["start"] + 0.25),
                    "text": " ".join(w["text"] for w in bucket).strip(),
                }
            )
        return chunks
    except Exception as exc:
        if logger:
            logger.warn(f"Whisper caption timing unavailable, using phrase fallback ({exc.__class__.__name__})")
        return None


def _ass_header(palette: dict[str, str]) -> str:
    primary = ass_color(palette["text_primary"])
    secondary = ass_color(palette["text_secondary"])
    back = "&H14000000&"
    outline = "&H00101010&"
    return "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            "PlayResX: 1080",
            "PlayResY: 1920",
            "WrapStyle: 2",
            "ScaledBorderAndShadow: yes",
            "YCbCr Matrix: TV.709",
            "",
            "[V4+ Styles]",
            "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
            f"Style: TVCaption,Arial,58,{primary},{secondary},{outline},{back},1,0,0,0,100,100,0,0,1,3,1,2,72,72,250,1",
            "",
            "[Events]",
            "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
        ]
    )


def generate_ass_captions(
    narration_text: str,
    voice_wav: Path,
    ass_path: Path,
    palette: dict[str, str],
    logger: Any = None,
) -> dict[str, Any]:
    audio_dur = max(0.1, media_duration(voice_wav))
    chunks = _chunks_from_whisper(voice_wav, logger=logger)
    mode = "whisper_word_level" if chunks else "phrase_fallback"
    if not chunks:
        if logger:
            logger.warn("Using phrase-level captions with approximate timings")
        chunks = _chunks_from_phrase_fallback(narration_text, audio_dur)

    lines = [_ass_header(palette)]
    for ch in chunks:
        start = max(0.0, float(ch["start"]))
        end = max(start + 0.2, float(ch["end"]))
        text = _sanitize_ass_text(str(ch["text"]))
        if not text:
            continue
        styled = _highlight_keywords(text, palette["accent"], palette["text_primary"])
        # subtle pop animation and static bottom-center position within safe area
        prefix = r"{\an2\pos(540,1590)\bord3\shad1\fsp0\t(0,120,\fscx104\fscy104)}"
        lines.append(f"Dialogue: 0,{seconds_to_ass(start)},{seconds_to_ass(end)},TVCaption,,0,0,0,,{prefix}{styled}")

    ass_path.parent.mkdir(parents=True, exist_ok=True)
    ass_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    events_json_path = ass_path.with_suffix(".json")
    events_json_path.write_text(
        json.dumps(
            [
                {
                    "start": round(max(0.0, float(ch["start"])), 3),
                    "end": round(max(float(ch["end"]), float(ch["start"]) + 0.2), 3),
                    "text": _sanitize_ass_text(str(ch["text"])),
                }
                for ch in chunks
                if _sanitize_ass_text(str(ch["text"]))
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    if logger:
        logger.step(f"Captions generated: {mode} ({len(chunks)} caption events)")
    return {"mode": mode, "count": len(chunks), "duration": audio_dur, "events_json": str(events_json_path)}
