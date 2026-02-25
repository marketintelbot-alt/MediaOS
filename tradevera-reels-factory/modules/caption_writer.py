from __future__ import annotations

from .utils import sanitize_title


def _hashtags() -> list[str]:
    return [
        "#trading",
        "#daytrading",
        "#riskmanagement",
        "#tradingpsychology",
        "#trader",
        "#priceaction",
        "#discipline",
        "#execution",
        "#tradingeducation",
        "#tradevera",
    ]


def build_caption_text(script: dict) -> str:
    idea = sanitize_title(script.get("idea", "TradeVera reel"), 120)
    points = script.get("points", [])[:3]
    lines = [
        f"{idea}.",
        "",
        "TradeVera focus:",
    ]
    for p in points:
        lines.append(f"- {p}")
    lines.extend(
        [
            "",
            script.get("cta", "Follow TradeVera for daily edge."),
            "",
            " ".join(_hashtags()),
        ]
    )
    return "\n".join(lines).strip() + "\n"


def build_hooks_text(script: dict) -> str:
    hooks = script.get("alt_hooks") or []
    return "\n".join(hooks[:5]).strip() + "\n"
