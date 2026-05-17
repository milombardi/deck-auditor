"""One-clear-takeaway check."""

import json
from dataclasses import dataclass
from typing import List

from anthropic import Anthropic

import config
from cost import CostTracker
from extractor import Slide


@dataclass
class TakeawayFlag:
    slide_index: int
    issue: str            # short tag
    detail: str
    rewrite: str          # action: tighten or split


_SYSTEM = (
    "You are a sharp slide editor. Every slide should make ONE point. "
    "You find slides that crowd in multiple competing points, or where "
    "the headline doesn't match the body's actual takeaway, or where "
    "the takeaway is buried/hedged/unclear. Output strict JSON only."
)

_USER = """Slide {idx}:
TITLE: {title}
BODY:
{body}

Judge this slide on three things:
1. main_argument: the single strongest claim a reader walks away with (one sentence)
2. competing_points: any other arguments that fight for the same airtime (list of short phrases; empty if none)
3. headline_match: does the title state the main argument? true/false

Then return ONE of these verdicts in "verdict":
- "ok" — one clear point, headline matches, no fix needed
- "tighten" — the takeaway is buried, hedged, or competing; rewrite the slide around one point
- "split" — there are genuinely two or more separate arguments here; this should be multiple slides
- "headline_mismatch" — title is fine in voice but doesn't reflect the actual body takeaway

And return:
- "fix": a concrete recommendation. If verdict is "tighten" or "headline_mismatch", give a new headline (<=12 words) and one-line note on what to cut. If "split", say what the two or three slides should each say. If "ok", empty string.

Return strict JSON:
{{
  "main_argument": "...",
  "competing_points": ["..."],
  "headline_match": true,
  "verdict": "ok|tighten|split|headline_mismatch",
  "fix": "..."
}}
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
        on_progress=None) -> List[TakeawayFlag]:
    flags: List[TakeawayFlag] = []
    for s in slides:
        if not s.body_text and not s.title:
            continue
        prompt = _USER.format(
            idx=s.index,
            title=s.title or "(no title)",
            body=s.body_text[:3500] or "(empty)",
        )
        try:
            resp = client.messages.create(
                model=config.MODEL,
                max_tokens=600,
                system=_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as e:
            print(f"  [takeaway] slide {s.index} error: {e}")
            if on_progress:
                on_progress(s.index, len(slides))
            continue
        tracker.add(resp.usage)
        text = "".join(b.text for b in resp.content if getattr(b, "text", None))
        data = _extract_json(text) or {}
        verdict = data.get("verdict", "ok")
        if verdict == "ok":
            if on_progress:
                on_progress(s.index, len(slides))
            continue

        issue_map = {
            "tighten": "takeaway is buried or competing with other points",
            "split": "multiple separate arguments on one slide",
            "headline_mismatch": "headline doesn't match the body's actual point",
        }
        competing = data.get("competing_points") or []
        detail_bits = []
        if data.get("main_argument"):
            detail_bits.append(f"main argument: {data['main_argument']}")
        if competing:
            detail_bits.append("competing: " + "; ".join(competing[:4]))
        flags.append(TakeawayFlag(
            slide_index=s.index,
            issue=issue_map.get(verdict, verdict),
            detail=" | ".join(detail_bits),
            rewrite=str(data.get("fix") or "").strip(),
        ))
        if on_progress:
            on_progress(s.index, len(slides))
    return flags
