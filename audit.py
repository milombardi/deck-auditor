"""Deck Auditor — CLI entry point.

Usage:
    python audit.py path/to/deck.pptx [--meeting-minutes 30] [--max-cost 3]
                                       [--hard-cap 10] [--force] [--dry-run]
"""

import argparse
import os
import sys
from pathlib import Path

from anthropic import Anthropic

import config
from cost import CostTracker, confirm_or_exit, estimate
from extractor import extract
import density
import narrative
import redundancy
import report
import scoring
import takeaway
import voice


def _progress(label):
    def cb(i, total):
        print(f"  [{label}] {i}/{total}", end="\r", flush=True)
        if i == total:
            print()
    return cb


def main():
    p = argparse.ArgumentParser(description="Audit a .pptx deck.")
    p.add_argument("deck", help="path to .pptx file")
    p.add_argument("--meeting-minutes", type=int,
                   default=config.DEFAULT_MEETING_MINUTES)
    p.add_argument("--max-cost", type=float, default=config.DEFAULT_MAX_COST)
    p.add_argument("--hard-cap", type=float, default=config.DEFAULT_HARD_CAP)
    p.add_argument("--force", action="store_true",
                   help="bypass cost confirmation and slide hard-stop")
    p.add_argument("--dry-run", action="store_true",
                   help="print estimate and exit without calling the API")
    args = p.parse_args()

    deck_path = os.path.abspath(args.deck)
    if not os.path.exists(deck_path):
        print(f"File not found: {deck_path}", file=sys.stderr)
        sys.exit(1)
    if not deck_path.lower().endswith(".pptx"):
        print("Input must be a .pptx file.", file=sys.stderr)
        sys.exit(1)

    print(f"Extracting: {deck_path}")
    slides = extract(deck_path)
    if not slides:
        print("No slides found.", file=sys.stderr)
        sys.exit(1)

    # Deck size guardrails
    if len(slides) > config.SLIDE_HARD_STOP and not args.force:
        print(f"\nRefusing to run: {len(slides)} slides exceeds hard stop "
              f"({config.SLIDE_HARD_STOP}). Pass --force to override.",
              file=sys.stderr)
        sys.exit(2)
    if len(slides) > config.SLIDE_WARN:
        print(f"\nWarning: {len(slides)} slides is a lot. "
              f"This will be slow and costly.")

    # Cost estimate
    est = estimate(slides)
    print()
    print("Cost estimate")
    print(f"  slides:            {est.slide_count}")
    print(f"  words:             {est.word_count:,}")
    print(f"  est. input tokens: {est.input_tokens:,}")
    print(f"  est. output tokens:{est.output_tokens:,}")

    if args.dry_run:
        print(f"  estimated cost:    ${est.cost:.2f}")
        print("\nDry run. Exiting.")
        return

    confirm_or_exit(est, args.max_cost, args.hard_cap, args.force)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("\nANTHROPIC_API_KEY not set in environment.", file=sys.stderr)
        sys.exit(1)
    client = Anthropic(api_key=api_key)
    tracker = CostTracker()

    print("\nRunning checks…")

    print("- AI voice (regex pass)")
    voice_results = {"regex": voice.regex_scan(slides),
                     "deck_construction": voice.deck_construction_scan(slides),
                     "api": []}

    print("- AI voice (API pass)")
    voice_results["api"] = voice.api_scan(slides, client, tracker,
                                          on_progress=_progress("voice"))
    print(f"  running cost: {tracker.summary()}")

    print("- Density")
    density_flags = density.run(slides, args.meeting_minutes)

    print("- Narrative headlines")
    headline_flags = narrative.run(slides, client, tracker,
                                   on_progress=_progress("headlines"))
    print(f"  running cost: {tracker.summary()}")

    print("- One clear takeaway")
    takeaway_flags = takeaway.run(slides, client, tracker,
                                  on_progress=_progress("takeaway"))
    print(f"  running cost: {tracker.summary()}")

    print("- Redundancy")
    redundancy_flags = redundancy.run(slides, client, tracker)
    print(f"  running cost: {tracker.summary()}")

    print("\nScoring…")
    scores = scoring.score(slides, headline_flags, takeaway_flags,
                           voice_results, density_flags, redundancy_flags)

    print(f"  total: {scores.total}/100 — {scores.band}")
    print(f"  narrative={scores.narrative} takeaway={scores.takeaway} "
          f"voice={scores.voice} density={scores.density} "
          f"redundancy={scores.redundancy}")

    out_path = Path(deck_path).with_name(Path(deck_path).stem + "-audit.md")
    md = report.build(
        deck_path=deck_path,
        slides=slides,
        scores=scores,
        headline_flags=headline_flags,
        takeaway_flags=takeaway_flags,
        voice_flags=voice_results,
        density_flags=density_flags,
        redundancy_flags=redundancy_flags,
        actual_cost_summary=tracker.summary(),
    )
    out_path.write_text(md, encoding="utf-8")
    print(f"\nReport written: {out_path}")
    print(f"Final cost: {tracker.summary()}")


if __name__ == "__main__":
    main()
