"""Scoring logic. Each of five checks is 0-20. Total is 0-100. Harsh by design."""

from dataclasses import dataclass
from typing import Dict, List

import config
from extractor import Slide


@dataclass
class Scores:
    narrative: int        # 0-20
    takeaway: int         # 0-20
    voice: int            # 0-20
    density: int          # 0-20
    redundancy: int       # 0-20

    @property
    def total(self) -> int:
        return (self.narrative + self.takeaway + self.voice +
                self.density + self.redundancy)

    @property
    def band(self) -> str:
        t = self.total
        for threshold, label in config.BANDS:
            if t >= threshold:
                return label
        return "rebuild"


def _scale(rate: float, harshness: float = 1.5) -> int:
    """Map a violation rate (0..1+, higher = worse) to a 0-20 score.

    rate = 0    -> 20
    rate = 0.5  -> ~10 (with harshness=1.5)
    rate = 1+   -> 0
    """
    penalty = min(20.0, 20.0 * rate * harshness)
    return max(0, int(round(20.0 - penalty)))


def score(
    slides: List[Slide],
    headline_flags,
    takeaway_flags,
    voice_flags: Dict[str, list],
    density_flags,
    redundancy_flags,
) -> Scores:
    n_slides = max(1, len(slides))

    # Narrative: fraction of slides with a headline problem.
    narrative_slides = {f.slide_index for f in headline_flags if f.slide_index > 0}
    narrative = _scale(len(narrative_slides) / n_slides)

    # Takeaway: fraction of slides flagged for buried/competing/mismatch.
    takeaway_slides = {f.slide_index for f in takeaway_flags if f.slide_index > 0}
    takeaway = _scale(len(takeaway_slides) / n_slides)

    # Voice: weighted count of flags across regex+api+deck. Per-slide cap 6 to
    # stop one disaster slide from dragging the whole score to zero.
    per_slide_counts: Dict[int, int] = {}
    deck_voice_hits = 0
    for bucket_name, bucket in voice_flags.items():
        for f in bucket:
            if f.slide_index == 0:
                deck_voice_hits += 1
            else:
                per_slide_counts[f.slide_index] = per_slide_counts.get(f.slide_index, 0) + 1
    capped = sum(min(6, c) for c in per_slide_counts.values())
    # Roughly: 2 voice hits per slide is "bad", 4+ is "rebuild".
    voice_rate = (capped / n_slides) / 4.0 + (deck_voice_hits * 0.05)
    voice = _scale(voice_rate, harshness=1.2)

    # Density: per-slide flags (word/bullet/nesting) + deck-level runtime flag.
    density_slides = {f.slide_index for f in density_flags if f.slide_index > 0}
    deck_density = sum(1 for f in density_flags if f.slide_index == 0)
    density = _scale(len(density_slides) / n_slides + deck_density * 0.15)

    # Redundancy: every slide in a duplicate/restate cluster counts.
    redundant_slides = set()
    for r in redundancy_flags:
        for idx in r.slide_indices:
            if idx > 0:
                redundant_slides.add(idx)
    redundancy = _scale(len(redundant_slides) / n_slides, harshness=2.0)

    return Scores(narrative, takeaway, voice, density, redundancy)
