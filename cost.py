"""Cost estimation and live tracking."""

from dataclasses import dataclass
from typing import List
import sys

from config import (
    INPUT_COST_PER_MTOK, OUTPUT_COST_PER_MTOK,
    WORDS_PER_TOKEN, PROMPT_OVERHEAD_TOKENS_PER_SLIDE,
    OUTPUT_TOKENS_PER_SLIDE,
)
from extractor import Slide


@dataclass
class Estimate:
    word_count: int
    slide_count: int
    input_tokens: int
    output_tokens: int
    cost: float


def estimate(slides: List[Slide]) -> Estimate:
    total_words = sum(s.word_count for s in slides)
    # Content tokens (we send each slide once or twice across checks; budget 2x).
    content_tokens = int((total_words / WORDS_PER_TOKEN) * 2)
    overhead = PROMPT_OVERHEAD_TOKENS_PER_SLIDE * len(slides)
    input_tokens = content_tokens + overhead
    output_tokens = OUTPUT_TOKENS_PER_SLIDE * len(slides)

    cost = (
        input_tokens / 1_000_000 * INPUT_COST_PER_MTOK
        + output_tokens / 1_000_000 * OUTPUT_COST_PER_MTOK
    )
    return Estimate(total_words, len(slides), input_tokens, output_tokens, cost)


class CostTracker:
    """Tracks actual cost from API responses."""

    def __init__(self):
        self.input_tokens = 0
        self.output_tokens = 0

    def add(self, usage):
        # usage is anthropic Usage object with input_tokens / output_tokens
        self.input_tokens += getattr(usage, "input_tokens", 0) or 0
        self.output_tokens += getattr(usage, "output_tokens", 0) or 0

    @property
    def cost(self) -> float:
        return (
            self.input_tokens / 1_000_000 * INPUT_COST_PER_MTOK
            + self.output_tokens / 1_000_000 * OUTPUT_COST_PER_MTOK
        )

    def summary(self) -> str:
        return (
            f"input {self.input_tokens:,} tok, "
            f"output {self.output_tokens:,} tok, "
            f"cost ${self.cost:.3f}"
        )


def confirm_or_exit(est: Estimate, max_cost: float, hard_cap: float, force: bool):
    """Apply guardrails. Exits if user denies or hard cap exceeded."""
    print(f"  estimated cost:    ${est.cost:.2f}")
    if est.cost > hard_cap and not force:
        print(
            f"\nRefusing to run. Estimated cost ${est.cost:.2f} exceeds "
            f"hard cap ${hard_cap:.2f}. Pass --force to override.",
            file=sys.stderr,
        )
        sys.exit(2)
    if est.cost > max_cost and not force:
        resp = input(f"\nEstimated cost ${est.cost:.2f} exceeds soft cap "
                     f"${max_cost:.2f}. Proceed? y/n: ").strip().lower()
        if resp != "y":
            print("Aborted.")
            sys.exit(0)
