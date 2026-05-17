"""Density checks. No API needed."""

from dataclasses import dataclass
from typing import List

import config
from extractor import Slide


@dataclass
class DensityFlag:
    slide_index: int           # 0 = deck-level
    issue: str
    detail: str
    rewrite: str


def run(slides: List[Slide], meeting_minutes: int) -> List[DensityFlag]:
    flags: List[DensityFlag] = []

    for s in slides:
        if s.word_count > config.MAX_WORDS_PER_SLIDE:
            flags.append(DensityFlag(
                slide_index=s.index,
                issue="word count over 75",
                detail=f"{s.word_count} words on this slide",
                rewrite="Cut to one headline and three to five tight lines. "
                        "Move the rest to speaker notes or a backup slide.",
            ))
        if len(s.bullets) > config.MAX_BULLETS_PER_SLIDE:
            flags.append(DensityFlag(
                slide_index=s.index,
                issue=f"bullet count over {config.MAX_BULLETS_PER_SLIDE}",
                detail=f"{len(s.bullets)} bullets",
                rewrite="Group related bullets, cut the weakest, or split the slide.",
            ))
        nested = [b for b in s.bullets if b.level > 0]
        if nested:
            flags.append(DensityFlag(
                slide_index=s.index,
                issue="nested bullets",
                detail=f"{len(nested)} sub-bullets",
                rewrite="Flatten. If a sub-bullet matters, promote it to its own line "
                        "or its own slide. Sub-bullets read as noise.",
            ))

    # Deck-level runtime
    runtime = len(slides) * config.MINUTES_PER_SLIDE
    if runtime > meeting_minutes:
        flags.append(DensityFlag(
            slide_index=0,
            issue="deck too long for meeting",
            detail=(f"{len(slides)} slides at {config.MINUTES_PER_SLIDE} min/slide "
                    f"= {runtime} min, meeting is {meeting_minutes} min"),
            rewrite=(f"Cut to about {max(1, meeting_minutes // config.MINUTES_PER_SLIDE)} "
                     "slides. Move the rest to appendix."),
        ))

    return flags
