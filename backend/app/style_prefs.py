"""Structured style-preference scoring for the personalized summary.

Complements the free-text ``style_notes`` with weighted scores per style value,
so the user can nudge their style directly (the /style endpoint) and two close
styles can *blend*. Each nudge gently decays every score then adds to the chosen
one, so newer choices come to dominate and stale ones fade.

Pure functions over a plain ``{value: score}`` dict — deterministic + testable.
"""
from __future__ import annotations

import json

# value -> natural-language instruction injected into the agent prompt
TAXONOMY: dict[str, str] = {
    "story": "use story-based, narrative explanations",
    "bullets": "use concise bullet points",
    "sections": "organize under clear section headings",
    "simple": "explain simply, in plain beginner-friendly language",
    "technical": "include technical depth and precise terminology",
    "concise": "keep it short and to the point",
    "detailed": "be thorough and detailed",
    "examples": "use concrete examples and analogies",
}

# value -> short label for the UI chips
LABELS: dict[str, str] = {
    "story": "📖 Story",
    "bullets": "• Bullets",
    "sections": "▤ Sections",
    "simple": "🧒 Simpler",
    "technical": "🔬 Technical",
    "concise": "✂️ Shorter",
    "detailed": "📝 More detail",
    "examples": "💡 Examples",
}

BUMP = 1.5            # default weight added when the user picks a style
DECAY = 0.9          # multiply all scores before each nudge (older prefs fade)
MIX_THRESHOLD = 0.6  # blend the 2nd style when it's within this of the top
MAX_EFFECTIVE = 2    # at most this many styles emphasized at once


def valid_value(value: str) -> bool:
    return value in TAXONOMY


def normalize(scores) -> dict[str, float]:
    """Coerce to ``{known_value: float}``; drop unknown/garbage and <=0 noise kept."""
    out: dict[str, float] = {}
    if isinstance(scores, str):
        try:
            scores = json.loads(scores)
        except (TypeError, ValueError):
            scores = {}
    if isinstance(scores, dict):
        for k, v in scores.items():
            if k in TAXONOMY:
                try:
                    out[k] = round(float(v), 4)
                except (TypeError, ValueError):
                    continue
    return out


def bump(scores, value: str, delta: float = BUMP) -> dict[str, float]:
    """Decay all scores, then add ``delta`` to ``value``. Returns a new dict."""
    cur = normalize(scores)
    nxt = {k: round(v * DECAY, 4) for k, v in cur.items()}
    nxt[value] = round(nxt.get(value, 0.0) + float(delta), 4)
    # prune negligible scores so the dict stays clean
    return {k: v for k, v in nxt.items() if v > 0.05}


def effective_styles(scores) -> list[str]:
    """Top style(s): the highest-scoring value, plus the 2nd if it's close (blend)."""
    cur = normalize(scores)
    ranked = sorted(((v, s) for v, s in cur.items() if s > 0), key=lambda kv: kv[1], reverse=True)
    if not ranked:
        return []
    picked = [ranked[0][0]]
    for value, score in ranked[1:MAX_EFFECTIVE]:
        if ranked[0][1] - score <= MIX_THRESHOLD:
            picked.append(value)
    return picked


def emphasis_phrases(scores) -> list[str]:
    """The instruction phrases for the effective styles (top first)."""
    return [TAXONOMY[v] for v in effective_styles(scores)]


def sig(scores) -> str:
    """Stable signature of the effective styles — feeds the cache key so a style
    change regenerates the personalized summary."""
    cur = normalize(scores)
    return ";".join(f"{k}:{cur[k]}" for k in sorted(cur))


def options() -> list[dict[str, str]]:
    return [{"value": v, "label": LABELS.get(v, v.title()), "hint": TAXONOMY[v]} for v in TAXONOMY]
