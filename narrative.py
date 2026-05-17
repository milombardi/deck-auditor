"""Narrative-headline check. Titles should state a takeaway, not label a topic."""

import json
import re
from dataclasses import dataclass
from typing import List, Optional

from anthropic import Anthropic

import config
from cost import CostTracker
from extractor import Slide


@dataclass
class HeadlineFlag:
    slide_index: int
    quote: str
    why: str
    rewrite: str


_GENERIC = {
    "agenda", "introduction", "overview", "key takeaways", "takeaways",
    "next steps", "thank you", "questions", "appendix", "summary",
    "background", "our approach", "the approach", "market landscape",
    "executive summary", "objectives", "objective", "goals", "vision",
    "mission", "discussion", "conclusion", "context",
}


def _is_obvious_label(title: str) -> Optional[str]:
    t = title.strip().lower().rstrip(".:!?")
    if not t:
        return None
    if t in _GENERIC:
        return "generic section label"
    # Noun-phrase heuristic: no verb-like words and short.
    words = t.split()
    if len(words) <= 5 and not re.search(
        r"\b(is|are|was|were|has|have|had|does|do|did|can|will|should|"
        r"shows|drives|wins|builds|cuts|loses|grows|beats|fails|"
        r"makes|works|matters|stops|starts|owns|leads)\b", t
    ):
        # Likely a noun-phrase title.
        return "noun-phrase title (states a topic, not a point)"
    return None


_HEADLINE_SYSTEM = (
    "You are a sharp editor judging whether slide titles state a takeaway "
    "(a claim) or just label a topic. Output strict JSON only."
)

_HEADLINE_USER = """Decide if this slide TITLE states a clear takeaway/claim about the body, or whether it's a label/topic/category.

A takeaway makes a point (a verb, a stance, a conclusion). A label just names the area.

Examples:
- "Market Landscape" → label
- "The mid-market is consolidating fast" → takeaway
- "Our Approach" → label
- "We win by sequencing pilots, then scaling" → takeaway

Slide {idx}:
TITLE: {title}
BODY:
{body}

Return JSON: {{"is_takeaway": true|false, "rewrite": "headline that states the actual point from the body in <=12 words"}}
If it's already a takeaway, return {{"is_takeaway": true, "rewrite": ""}}.
"""


def _extract_json(text: str):
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def run(slides: List[Slide], client: Anthropic, tracker: CostTracker,
        on_progress=None) -> List[HeadlineFlag]:
    flags: List[HeadlineFlag] = []
    for s in slides:
        if not s.title:
            # Missing title is itself a flag.
            flags.append(HeadlineFlag(
                slide_index=s.index,
                quote="(no title)",
                why="slide has no headline at all",
                rewrite="Add a headline that states the single takeaway of this slide.",
            ))
            if on_progress:
                on_progress(s.index, len(slides))
            continue

        obvious = _is_obvious_label(s.title)
        if obvious:
            # Cheap path: ask the API only for the rewrite.
            rewrite = _api_rewrite(s, client, tracker)
            flags.append(HeadlineFlag(
                slide_index=s.index,
                quote=s.title,
                why=obvious,
                rewrite=rewrite or "Restate as the actual point the slide is making.",
            ))
            if on_progress:
                on_progress(s.index, len(slides))
            continue

        # Ask Claude to judge.
        prompt = _HEADLINE_USER.format(
            idx=s.index,
            title=s.title,
            body=s.body_text[:3000] or "(empty)",
        )
        try:
            resp = client.messages.create(
                model=config.MODEL,
                max_tokens=400,
                system=_HEADLINE_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            tracker.add(resp.usage)
            text = "".join(b.text for b in resp.content if getattr(b, "text", None))
            data = _extract_json(text) or {}
            if not data.get("is_takeaway", True):
                flags.append(HeadlineFlag(
                    slide_index=s.index,
                    quote=s.title,
                    why="title labels the topic instead of stating the point",
                    rewrite=str(data.get("rewrite") or "").strip()
                            or "Restate as the actual point the slide is making.",
                ))
        except Exception as e:
            print(f"  [narrative] slide {s.index} error: {e}")
        if on_progress:
            on_progress(s.index, len(slides))
    return flags


def _api_rewrite(s: Slide, client: Anthropic, tracker: CostTracker) -> str:
    try:
        resp = client.messages.create(
            model=config.MODEL,
            max_tokens=120,
            system=(
                "Rewrite a slide title so it states the actual takeaway of the "
                "body in 12 words or fewer. Plain language. Output the rewrite only."
            ),
            messages=[{
                "role": "user",
                "content": f"TITLE: {s.title}\n\nBODY:\n{s.body_text[:2500]}"
            }],
        )
        tracker.add(resp.usage)
        return "".join(b.text for b in resp.content if getattr(b, "text", None)).strip()
    except Exception:
        return ""
