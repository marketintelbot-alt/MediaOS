from __future__ import annotations

import random
import re
from typing import Any

from .utils import sanitize_title, seed_from_text

DEFAULT_CTA = "Follow TradeVera for daily edge."
ALT_CTAS = [
    "Follow TradeVera for daily edge.",
    "Follow TradeVera for execution + edge.",
    "Follow TradeVera for trader-level clarity.",
]

IDEA_PRESETS = [
    "Why most traders fail risk management",
    "Stop loss mistake that ruins good setups",
    "How to size positions without emotion",
    "Win rate vs expectancy: what actually matters",
    "Why overtrading kills your edge",
    "Revenge trading after a red day",
    "FOMO entries vs planned execution",
    "How to build a pre-market checklist",
    "Journal mistakes that keep repeating",
    "How to define invalidation before entry",
    "R multiple thinking for consistent traders",
    "Drawdown rules every trader needs",
    "When to skip a trade even if it looks good",
    "Setup quality vs market noise",
    "How pros handle losing streaks",
    "The position sizing formula traders ignore",
    "Breakout entry mistakes most traders make",
    "Why late entries destroy risk-reward",
    "Partial profits without sabotaging the trade",
    "News volatility and execution discipline",
    "Session timing: stop trading the dead hours",
    "A simple post-trade review framework",
    "Confluence is not a reason to force a trade",
    "How to protect capital during choppy markets",
    "Stop widening your stop loss",
    "Execution checklist before every trade",
    "Backtesting errors that create fake confidence",
    "How to reduce impulsive trades",
    "Process goals vs P and L goals",
    "Why traders confuse activity with progress",
]

TOPIC_RULES: list[tuple[tuple[str, ...], list[str]]] = [
    (
        ("risk", "position", "size", "sizing"),
        [
            "Define risk before the entry.",
            "Size the trade to the stop, not your emotions.",
            "Protect consistency before chasing upside.",
        ],
    ),
    (
        ("stop loss", "stop-loss", "stoploss", "stop"),
        [
            "Place stops where the setup breaks, not where pain starts.",
            "Adjust size first. Do not widen the stop to survive.",
            "Accept the loss fast and preserve execution quality.",
        ],
    ),
    (
        ("overtrading", "too many trades", "churn"),
        [
            "More trades do not create more edge.",
            "Cap your daily attempts before the session starts.",
            "Protect attention for A-plus setups only.",
        ],
    ),
    (
        ("revenge", "revenge trading", "red day"),
        [
            "After a loss, reduce size before you reduce standards.",
            "Do not let one trade set the next trade's risk.",
            "Step away long enough to reset execution quality.",
        ],
    ),
    (
        ("fomo", "late entry", "chase", "chasing"),
        [
            "If the entry is late, the risk is wrong.",
            "Missing one move is cheaper than forcing a bad fill.",
            "Trade location, not urgency.",
        ],
    ),
    (
        ("discipline", "psychology", "mental", "mindset"),
        [
            "Trade the plan, not the last result.",
            "Reduce decision count with clear setup rules.",
            "Journal execution mistakes and repeat fixes.",
        ],
    ),
    (
        ("expectancy", "win rate", "r multiple", "r-multiple", "rr", "risk-reward"),
        [
            "Win rate alone can hide weak expectancy.",
            "Track average winner, average loser, and execution quality.",
            "Protect asymmetry instead of chasing hit rate.",
        ],
    ),
    (
        ("drawdown", "losing streak", "streak"),
        [
            "Define drawdown limits before the market tests you.",
            "Cut size when execution degrades, not after damage compounds.",
            "Survival first. Recovery comes from clean process.",
        ],
    ),
    (
        ("checklist", "pre-market", "premarket", "routine"),
        [
            "Use a checklist to remove avoidable decisions.",
            "Confirm levels, context, and risk before the open.",
            "Checklist discipline improves consistency under speed.",
        ],
    ),
    (
        ("journal", "review", "post-trade", "debrief"),
        [
            "Review execution quality before reviewing P and L.",
            "Log mistakes as patterns, not isolated excuses.",
            "A good journal turns losses into process upgrades.",
        ],
    ),
    (
        ("breakout", "breakdowns", "pullback", "entry"),
        [
            "The setup is only valid where invalidation is clear.",
            "Entry precision matters because size follows location.",
            "Skip trades that force wide risk for average reward.",
        ],
    ),
    (
        ("news", "volatility", "cpi", "fomc"),
        [
            "Volatility is not edge unless your process adapts to it.",
            "Wider spreads require smaller size and cleaner timing.",
            "If context is unstable, protect capital and wait.",
        ],
    ),
    (
        ("session", "hours", "london", "new york", "ny open"),
        [
            "Trade the hours that match your setup, not every hour.",
            "Most bad trades happen in low-quality time windows.",
            "Session discipline protects focus and decision quality.",
        ],
    ),
    (
        ("confluence", "noise", "setup vs noise"),
        [
            "More signals do not fix a weak setup.",
            "Separate clean triggers from market noise.",
            "Confluence matters only when risk is still efficient.",
        ],
    ),
    (
        ("backtest", "backtesting", "data"),
        [
            "Backtests fail when rules are vague or curve-fit.",
            "Test execution rules you can actually follow live.",
            "Use data to tighten process, not validate bias.",
        ],
    ),
]



def _normalize_idea(idea: str) -> str:
    idea = re.sub(r"\s+", " ", idea or "").strip()
    return sanitize_title(idea, 140)



def suggest_ideas(limit: int | None = None) -> list[str]:
    ideas = list(IDEA_PRESETS)
    return ideas if limit is None else ideas[: max(0, limit)]



def _topic_points(idea: str) -> list[str]:
    lower = idea.lower()
    scored: list[tuple[int, list[str]]] = []
    for keys, points in TOPIC_RULES:
        score = sum(1 for k in keys if k in lower)
        if score:
            scored.append((score, points))

    if scored:
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]

    return [
        "Filter for clean setups and skip noise.",
        "Predefine risk and invalidation before entry.",
        "Review execution quality, not just P and L.",
    ]



def _hook_variants(idea: str) -> list[str]:
    core = idea.rstrip(".?!")
    low = core.lower()
    hooks = [
        f"{core}: the execution gap most traders miss.",
        f"Most traders get this wrong: {low}.",
        f"Your edge leaks here: {low}.",
        f"TradeVera breakdown: {low}.",
        f"If you want consistency, fix this first: {low}.",
        f"This one habit breaks your process: {low}.",
        f"The trader-level version of this: {low}.",
    ]
    # preserve order while deduping
    out: list[str] = []
    seen: set[str] = set()
    for h in hooks:
        key = h.lower()
        if key not in seen:
            seen.add(key)
            out.append(h)
    return out



def generate_script(idea: str, target_length: int, style: str = "tradevera_premium") -> dict[str, Any]:
    idea = _normalize_idea(idea)
    if not idea:
        raise ValueError("Idea text is required")

    rnd = random.Random(seed_from_text(f"{idea}|{target_length}|{style}"))
    point_pool = _topic_points(idea)
    point_count = 3 if target_length >= 24 else 2
    points = point_pool[:point_count]
    hook_options = _hook_variants(idea)
    hook = hook_options[0]
    cta = ALT_CTAS[rnd.randrange(len(ALT_CTAS))]

    bridge_options = [
        "Execution beats excitement. Protect the process.",
        "Edge comes from repeatable decisions under pressure.",
        "Discipline compounds faster than hype.",
        "Process first. Outcome second.",
    ]
    bridge = bridge_options[rnd.randrange(len(bridge_options))]

    narration_parts = [hook, *points, bridge, cta]
    caption_narration = " ".join(narration_parts)
    narration = caption_narration
    # Micro-pauses for a calmer finance narrator pace.
    narration = narration.replace(": ", ": ... ")
    narration = narration.replace(". ", ". ... ")

    visual_plan = [
        {"segment": "hook", "template": "title_card", "intent": "large hook text in first 2 seconds"},
        {"segment": "point_1", "template": "three_rules_widget", "intent": "numbered process steps"},
        {"segment": "point_2", "template": "myth_vs_fact", "intent": "myth versus execution reality"},
        {"segment": "point_3", "template": "risk_formula", "intent": "quant style formula emphasis"},
        {"segment": "support", "template": "mini_chart", "intent": "equity curve / drawdown context"},
        {"segment": "cta", "template": "checklist", "intent": "clean CTA close with TradeVera branding"},
    ]

    return {
        "hook": hook,
        "points": points,
        "cta": cta,
        "visual_plan": visual_plan,
        "narration": narration,
        "caption_narration": caption_narration,
        "style": style,
        "idea": idea,
        "target_length": target_length,
        "alt_hooks": hook_options[:5],
        "idea_presets": suggest_ideas(12),
    }
