"""Redundancy check: cluster slides by argument, flag duplicates and restates."""

import json
from dataclasses import dataclass
from typing import List

from anthropic import Anthropic

import config
from cost import CostTracker
from extractor import Slide


@dataclass
class RedundancyFlag:
    slide_indices: List[int]
    issue: str          # "duplicate", "near-duplicate", or "restates earlier slide"
    summary: str        # what the cluster is about
    rewrite: str        # cut/merge recommendation


_SYSTEM = (
    "You are a sharp deck editor. You read a list of slide summaries and "
    "find clusters where slides repeat the same argument, or where a later "
    "slide just restates something already said. Output strict JSON only."
)

_USER = """Here are the slides in this deck. Each line is: [slide N] TITLE — short body summary

{listing}

Find clusters where:
- duplicate: two or more slides make the exact same argument
- near-duplicate: two or more slides argue substantially the same point with minor reframing
- restates earlier slide: a slide whose only job is to repeat or summarize a point already established

Return strict JSON:
{{
  "clusters": [
    {{
      "slides": [3, 9],
      "issue": "duplicate|near-duplicate|restates earlier slide",
      "summary": "the shared point in one short sentence",
      "fix": "cut/merge/keep recommendation: which slide to keep, which to cut, and why"
    }}
  ]
}}

If nothing is redundant, return {{"clusters": []}}. Be strict — different angles on the same topic are NOT duplicates.
"""


def _summarize(s: Slide, max_chars: int = 220) -> str:
    body = (s.body_text or "").replace("\n", " ").strip()
    if len(body) > max_chars:
        body = body[:max_chars] + "…"
    title = s.title or "(no title)"
    return f"[slide {s.index}] {title} — {body}"


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


def run(slides: List[Slide], client: Anthropic, tracker: CostTracker) -> List[RedundancyFlag]:
    if len(slides) < 2:
        return []
    listing = "\n".join(_summarize(s) for s in slides)
    prompt = _USER.format(listing=listing)
    try:
        resp = client.messages.create(
            model=config.MODEL,
            max_tokens=2000,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        print(f"  [redundancy] error: {e}")
        return []
    tracker.add(resp.usage)
    text = "".join(b.text for b in resp.content if getattr(b, "text", None))
    data = _extract_json(text) or {}
    out: List[RedundancyFlag] = []
    for c in data.get("clusters", []):
        try:
            idxs = [int(x) for x in c.get("slides", [])]
        except (TypeError, ValueError):
            continue
        if len(idxs) < 1:
            continue
        out.append(RedundancyFlag(
            slide_indices=idxs,
            issue=str(c.get("issue", "duplicate"))[:60],
            summary=str(c.get("summary", ""))[:300],
            rewrite=str(c.get("fix", ""))[:400],
        ))
    return out
