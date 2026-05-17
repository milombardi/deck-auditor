"""AI-voice check. Hybrid: regex/word-list + Claude API for contextual tells."""

import json
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from anthropic import Anthropic

import config
from cost import CostTracker
from extractor import Slide


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------

@dataclass
class Flag:
    slide_index: int            # 0 for deck-level
    category: str               # e.g. "A: hype verb"
    quote: str
    rewrite: str
    note: str = ""              # optional context (mostly for deck-level)


# ---------------------------------------------------------------------------
# Regex layer (Categories A, B, C, G, H, I, J, M)
# ---------------------------------------------------------------------------

def _whole_word_pattern(words: List[str]) -> re.Pattern:
    # Sort longest first so multi-word phrases win.
    escaped = sorted((re.escape(w) for w in words), key=len, reverse=True)
    return re.compile(r"(?i)(?<![A-Za-z])(" + "|".join(escaped) + r")(?![A-Za-z])")


def _find_sentence(text: str, idx: int) -> str:
    """Return the sentence containing position idx."""
    start = max(text.rfind(".", 0, idx), text.rfind("!", 0, idx),
                text.rfind("?", 0, idx), text.rfind("\n", 0, idx)) + 1
    end_candidates = [
        text.find(".", idx), text.find("!", idx),
        text.find("?", idx), text.find("\n", idx)
    ]
    end_candidates = [e for e in end_candidates if e != -1]
    end = min(end_candidates) + 1 if end_candidates else len(text)
    return text[start:end].strip()


def _rewrite_for_match(category_letter: str, word: str, sentence: str) -> str:
    """Suggest a quick swap for the regex categories."""
    swaps = {
        "leverage": "use", "utilize": "use", "harness": "use",
        "facilitate": "help", "optimize": "improve",
        "streamline": "simplify", "transform": "change",
        "revolutionize": "change", "empower": "let", "unleash": "release",
        "unlock": "open up", "delve": "look at", "dive": "look at",
        "embark": "start", "navigate": "handle", "foster": "build",
        "cultivate": "build", "amplify": "boost", "spearhead": "lead",
        "championed": "led", "showcase": "show", "exemplify": "show",
        "epitomize": "show", "synthesize": "combine", "illuminate": "show",
        "manifest": "show", "galvanize": "rally", "permeate": "spread through",
        "resonate": "land", "underscore": "make clear", "immerse": "go deep into",
        "elucidate": "explain", "substantiate": "back up", "encompass": "cover",
        "pioneer": "lead", "transcend": "go beyond",
        "robust": "strong", "seamless": "smooth", "seamlessly": "smoothly",
        "holistic": "whole-picture", "comprehensive": "complete",
        "cutting-edge": "new", "innovative": "new", "dynamic": "active",
        "scalable": "able to grow", "transformative": "change-driving",
        "groundbreaking": "new", "unprecedented": "first-of-its-kind",
        "remarkable": "notable", "compelling": "strong", "captivating": "strong",
        "riveting": "gripping", "nuanced": "detailed", "profound": "deep",
        "impactful": "useful", "pivotal": "key", "paramount": "top",
        "crucial": "key", "bespoke": "custom", "esteemed": "respected",
        "meticulous": "careful", "vibrant": "lively", "intricate": "complex",
        "tapestry": "mix", "landscape": "market", "journey": "process",
        "beacon": "leader", "treasure trove": "set", "labyrinth": "maze",
        "bastion": "stronghold", "realm": "area", "zeitgeist": "mood",
        "fabric": "structure", "mosaic": "mix", "spectrum": "range",
        "ecosystem": "system", "arena": "market", "frontier": "edge",
        "paradigm": "model", "crossroads": "turning point",
        "intersection": "overlap", "unsung hero": "overlooked driver",
        "furthermore": "also", "moreover": "also", "additionally": "also",
        "consequently": "so", "subsequently": "then", "nevertheless": "still",
        "indeed": "(drop)", "essentially": "(drop)", "fundamentally": "at heart",
        "ultimately": "in the end", "specifically": "(drop)",
        "certainly": "(drop)", "notably": "(drop)", "accordingly": "so",
        "truly": "(drop)", "genuinely": "(drop)", "simply": "(drop)",
        "undoubtedly": "(drop)", "absolutely": "(drop)", "completely": "(drop)",
        "entirely": "(drop)", "particularly": "(drop)",
        "represents": "is", "reflects": "shows", "embodies": "is",
        "signifies": "means", "exemplifies": "shows", "underscores": "shows",
        "highlights": "shows", "emphasizes": "stresses", "illustrates": "shows",
        "demonstrates": "shows", "speaks to": "shows",
        "speaks volumes about": "shows",
    }
    w_lower = word.lower()
    if w_lower in swaps:
        suggestion = swaps[w_lower]
        if suggestion == "(drop)":
            return f"Drop \"{word}\" — the sentence works without it."
        # Rewrite sentence with swap if it fits cleanly.
        new = re.sub(r"(?i)(?<![A-Za-z])" + re.escape(word) + r"(?![A-Za-z])",
                     suggestion, sentence, count=1)
        return new.strip()
    if category_letter == "I":  # hedging phrase
        new = re.sub(r"(?i)" + re.escape(word) + r"\s*", "", sentence, count=1)
        return new.strip() or "Drop the hedge; state the claim directly."
    if category_letter == "M":
        return ("Lead with the subject and an active verb. "
                f"Example: instead of \"{word}…\", say what the thing actually does.")
    return f"Cut \"{word}\" or replace with plain wording."


_REGEX_BUCKETS = [
    ("A: hype verb", "A", config.CATEGORY_A_HYPE_VERBS),
    ("B: hollow adjective", "B", config.CATEGORY_B_HOLLOW_ADJECTIVES),
    ("C: metaphor crutch", "C", config.CATEGORY_C_METAPHOR_CRUTCHES),
    ("G: stuffy connective", "G", config.CATEGORY_G_STUFFY_CONNECTIVES),
    ("H: empty intensifier", "H", config.CATEGORY_H_EMPTY_INTENSIFIERS),
    ("I: vague hedging", "I", config.CATEGORY_I_VAGUE_HEDGING),
    ("J: symbolic verb", "J", config.CATEGORY_J_SYMBOLIC_VERBS),
]


def regex_scan(slides: List[Slide]) -> List[Flag]:
    flags: List[Flag] = []
    patterns = [(label, letter, _whole_word_pattern(words))
                for label, letter, words in _REGEX_BUCKETS]

    for s in slides:
        text = s.all_text
        if not text:
            continue
        for label, letter, pat in patterns:
            for m in pat.finditer(text):
                sentence = _find_sentence(text, m.start())
                flags.append(Flag(
                    slide_index=s.index,
                    category=label,
                    quote=sentence or m.group(0),
                    rewrite=_rewrite_for_match(letter, m.group(0), sentence),
                ))

        # Category M: -ing openers (must start a sentence/bullet)
        for opener in config.CATEGORY_M_ING_OPENERS:
            pat = re.compile(rf"(?m)(?:^|(?<=[.!?]\s)){re.escape(opener)}\b[^.\n]*[.\n]?")
            for m in pat.finditer(text):
                quote = m.group(0).strip()
                flags.append(Flag(
                    slide_index=s.index,
                    category="M: -ing opener",
                    quote=quote,
                    rewrite=_rewrite_for_match("M", opener, quote),
                ))
    return flags


# ---------------------------------------------------------------------------
# Deck-level construction counts (Category D + K)
# ---------------------------------------------------------------------------

def deck_construction_scan(slides: List[Slide]) -> List[Flag]:
    flags: List[Flag] = []
    all_text = "\n".join(s.all_text for s in slides)

    # K: em-dashes
    em_count = len(re.findall(r"—", all_text))
    if em_count > config.EM_DASH_DECK_LIMIT:
        flags.append(Flag(
            slide_index=0,
            category="K: em-dash overuse",
            quote=f"{em_count} em-dashes across the deck",
            rewrite="Replace em-dashes with periods or commas. Two per deck is plenty.",
        ))

    # D: from X to Y
    from_to = len(re.findall(r"(?i)\bfrom\s+\w[\w\s\-]{0,30}?\s+to\s+\w", all_text))
    if from_to >= config.FROM_X_TO_Y_LIMIT:
        flags.append(Flag(
            slide_index=0,
            category="D: 'from X to Y' overuse",
            quote=f"\"from X to Y\" appears {from_to} times",
            rewrite="Vary the construction. State the change directly without the formula.",
        ))

    whether_or = len(re.findall(r"(?i)\bwhether\s+\w[\w\s\-]{0,30}?\s+or\s+\w", all_text))
    if whether_or >= config.WHETHER_X_OR_Y_LIMIT:
        flags.append(Flag(
            slide_index=0,
            category="D: 'whether X or Y' overuse",
            quote=f"\"whether X or Y\" appears {whether_or} times",
            rewrite="Pick the case that matters and state it. Skip the dichotomy.",
        ))

    # Cadence: count "quiet"
    quiet_hits = len(re.findall(r"(?i)\bquiet\b", all_text))
    if quiet_hits >= 2:
        flags.append(Flag(
            slide_index=0,
            category="P: 'quiet' tic",
            quote=f"\"quiet\" appears {quiet_hits} times",
            rewrite="Find concrete words for what's actually happening. \"Quiet\" is filler.",
        ))

    # "The ones who..."
    the_ones = len(re.findall(r"(?i)\bthe ones who\b", all_text))
    if the_ones >= 1:
        flags.append(Flag(
            slide_index=0,
            category="P: 'the ones who' construction",
            quote=f"\"the ones who\" appears {the_ones} times",
            rewrite="Name the actor and the action. Skip the rhetorical setup.",
        ))

    return flags


# ---------------------------------------------------------------------------
# API layer (Categories D contextual, E, F, K nuanced, L, N, O, P phrasing)
# ---------------------------------------------------------------------------

_VOICE_API_SYSTEM = (
    "You are a sharp editor. You find AI-generated voice tells in slide copy "
    "and rewrite them in plain, active English. Output strict JSON only."
)

_VOICE_API_USER = """You are reviewing slide copy for these AI-voice tells (don't flag anything outside this list):

D. Construction patterns: "It's not X, it's Y" / "It's not just X, it's Y" / "Not only X but also Y" / "X isn't just about Y. It's about Z."
E. Opener clichés: "In today's fast-paced world", "In today's digital age", "In today's [adj] landscape", "In the realm of", "In the ever-evolving", "Imagine a world where", "At its core", "When it comes to"
F. Transition tics: "But here's the thing", "Here's the kicker/catch", "Here's why this matters", "The catch?", "The kicker?", "Let's unpack this", "Let's dive in", "At the end of the day", "Needless to say", "That said", "With that in mind"
K. Punctuation: mid-sentence bolding for emphasis (you can't see formatting, so only flag if the slide has many colons followed by sentence fragments — 3+)
L. Structural: tricolons of abstract nouns (e.g., "speed, scale, sophistication"), or all bullets exactly identical length/rhythm
N. Fake specificity: fictional example names ("Sarah Chen", "John Smith"), generic product references ("the tool/platform/solution") used instead of real names, stats without dates/sources, suspiciously round percentages without attribution
O. Rhetorical question tics: self-posed questions used as transitions ("So what does this mean?" "Why does this matter?" "What's next?"), or question-as-headline that isn't earning its place
P. Cadence: identical sentence rhythm slide-after-slide, same H1/H2 phrasing repeating (we'll check across-deck; for this slide only flag if every sentence has the same length/structure)

Slide {idx}:
TITLE: {title}
BODY:
{body}

Return JSON in exactly this shape:
{{
  "flags": [
    {{"category": "E: opener cliché", "quote": "exact phrase from the slide", "rewrite": "plain-language rewrite"}}
  ]
}}

Rules for rewrites: short words, active voice, no hype, sounds like a person talking, original meaning intact. If nothing to flag, return {{"flags": []}}.
"""


def _extract_json(text: str) -> Optional[dict]:
    # Find the first { ... } block.
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def api_scan(slides: List[Slide], client: Anthropic, tracker: CostTracker,
             on_progress=None) -> List[Flag]:
    flags: List[Flag] = []
    for s in slides:
        if not s.body_text and not s.title:
            continue
        prompt = _VOICE_API_USER.format(
            idx=s.index,
            title=s.title or "(no title)",
            body=s.body_text[:4000] or "(empty)",
        )
        try:
            resp = client.messages.create(
                model=config.MODEL,
                max_tokens=1200,
                system=_VOICE_API_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as e:
            print(f"  [voice api] slide {s.index} error: {e}")
            continue
        tracker.add(resp.usage)
        text = "".join(b.text for b in resp.content if getattr(b, "text", None))
        data = _extract_json(text) or {"flags": []}
        for f in data.get("flags", []):
            flags.append(Flag(
                slide_index=s.index,
                category=str(f.get("category", "voice"))[:80],
                quote=str(f.get("quote", ""))[:500],
                rewrite=str(f.get("rewrite", ""))[:500],
            ))
        if on_progress:
            on_progress(s.index, len(slides))
    return flags


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

def run(slides: List[Slide], client: Anthropic, tracker: CostTracker,
        on_progress=None) -> Dict[str, List[Flag]]:
    return {
        "regex": regex_scan(slides),
        "deck_construction": deck_construction_scan(slides),
        "api": api_scan(slides, client, tracker, on_progress=on_progress),
    }
