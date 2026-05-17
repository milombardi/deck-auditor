"""Markdown report assembly. The report obeys its own rules: plain language, no hype."""

from dataclasses import asdict
from typing import Dict, List

from extractor import Slide
from scoring import Scores


def _severity_for_slide(idx: int, headline_flags, takeaway_flags,
                        voice_flags, density_flags, redundancy_flags) -> int:
    """Rough severity score for ordering top fixes."""
    score = 0
    score += 4 * sum(1 for f in headline_flags if f.slide_index == idx)
    score += 4 * sum(1 for f in takeaway_flags if f.slide_index == idx)
    score += 3 * sum(1 for r in redundancy_flags if idx in r.slide_indices)
    score += 2 * sum(1 for f in density_flags if f.slide_index == idx)
    for bucket in voice_flags.values():
        score += sum(1 for f in bucket if f.slide_index == idx)
    return score


def _top_fixes(slides, headline_flags, takeaway_flags, voice_flags,
               density_flags, redundancy_flags, n=5) -> List[str]:
    ranked = []
    for s in slides:
        sev = _severity_for_slide(s.index, headline_flags, takeaway_flags,
                                  voice_flags, density_flags, redundancy_flags)
        if sev == 0:
            continue
        # Pick the most impactful single issue on this slide.
        primary = None
        for f in headline_flags:
            if f.slide_index == s.index:
                primary = ("headline", f.quote, f.rewrite)
                break
        if not primary:
            for f in takeaway_flags:
                if f.slide_index == s.index:
                    primary = ("takeaway", f.issue, f.rewrite)
                    break
        if not primary:
            for r in redundancy_flags:
                if s.index in r.slide_indices:
                    primary = ("redundant", r.summary, r.rewrite)
                    break
        if not primary:
            for f in density_flags:
                if f.slide_index == s.index:
                    primary = ("density", f.issue, f.rewrite)
                    break
        if not primary:
            for bucket in voice_flags.values():
                for f in bucket:
                    if f.slide_index == s.index:
                        primary = ("voice", f.quote, f.rewrite)
                        break
                if primary:
                    break
        if primary:
            ranked.append((sev, s.index, s.title or "(no title)", primary))

    ranked.sort(key=lambda x: -x[0])
    out = []
    for _, idx, title, (kind, what, fix) in ranked[:n]:
        out.append(f"- **Slide {idx} — {title}** ({kind}): {what}\n  - Fix: {fix}")
    return out


def _quote_block(text: str, limit: int = 280) -> str:
    t = (text or "").strip().replace("\n", " ")
    if len(t) > limit:
        t = t[:limit] + "…"
    return f"> {t}"


def build(
    deck_path: str,
    slides: List[Slide],
    scores: Scores,
    headline_flags,
    takeaway_flags,
    voice_flags: Dict[str, list],
    density_flags,
    redundancy_flags,
    actual_cost_summary: str,
) -> str:
    lines: List[str] = []
    lines.append(f"# Deck Audit: {deck_path.split('/')[-1]}")
    lines.append("")
    lines.append(f"**Score: {scores.total}/100 — {scores.band}**")
    lines.append("")
    lines.append("| Check | Score |")
    lines.append("|---|---|")
    lines.append(f"| Narrative headlines | {scores.narrative}/20 |")
    lines.append(f"| One clear takeaway | {scores.takeaway}/20 |")
    lines.append(f"| AI voice | {scores.voice}/20 |")
    lines.append(f"| Density | {scores.density}/20 |")
    lines.append(f"| Redundancy | {scores.redundancy}/20 |")
    lines.append("")

    # Top 5 fixes
    lines.append("## Top 5 fixes")
    lines.append("")
    fixes = _top_fixes(slides, headline_flags, takeaway_flags,
                       voice_flags, density_flags, redundancy_flags, n=5)
    if fixes:
        lines.extend(fixes)
    else:
        lines.append("No flags. The deck is ready.")
    lines.append("")

    # Deck-level findings
    deck_density = [f for f in density_flags if f.slide_index == 0]
    deck_voice_all = []
    for bucket in voice_flags.values():
        deck_voice_all.extend(f for f in bucket if f.slide_index == 0)

    if deck_density or deck_voice_all or redundancy_flags:
        lines.append("## Deck-level findings")
        lines.append("")
        for f in deck_density:
            lines.append(f"- **Density** — {f.issue}. {f.detail}.")
            lines.append(f"  - Fix: {f.rewrite}")
        for f in deck_voice_all:
            lines.append(f"- **Voice — {f.category}**: {f.quote}")
            lines.append(f"  - Fix: {f.rewrite}")
        for r in redundancy_flags:
            slides_str = ", ".join(str(i) for i in r.slide_indices)
            lines.append(f"- **Redundancy ({r.issue})** — slides {slides_str}: {r.summary}")
            lines.append(f"  - Fix: {r.rewrite}")
        lines.append("")

    # Slide-by-slide
    lines.append("## Slide-by-slide")
    lines.append("")
    for s in slides:
        s_headlines = [f for f in headline_flags if f.slide_index == s.index]
        s_takeaways = [f for f in takeaway_flags if f.slide_index == s.index]
        s_density = [f for f in density_flags if f.slide_index == s.index]
        s_voice = []
        for bucket in voice_flags.values():
            s_voice.extend(f for f in bucket if f.slide_index == s.index)
        s_red = [r for r in redundancy_flags if s.index in r.slide_indices]

        if not (s_headlines or s_takeaways or s_density or s_voice or s_red):
            continue  # skip clean slides

        title = s.title or "(no title)"
        lines.append(f"### Slide {s.index}: {title}")
        lines.append("")

        for f in s_headlines:
            lines.append(f"- **Headline** — {f.why}")
            lines.append(_quote_block(f.quote))
            lines.append(f"  - Rewrite: {f.rewrite}")
        for f in s_takeaways:
            lines.append(f"- **Takeaway** — {f.issue}")
            if f.detail:
                lines.append(f"  - {f.detail}")
            if f.rewrite:
                lines.append(f"  - Fix: {f.rewrite}")
        for f in s_density:
            lines.append(f"- **Density** — {f.issue} ({f.detail})")
            lines.append(f"  - Fix: {f.rewrite}")
        for f in s_voice:
            lines.append(f"- **Voice — {f.category}**")
            lines.append(_quote_block(f.quote))
            lines.append(f"  - Rewrite: {f.rewrite}")
        for r in s_red:
            others = [i for i in r.slide_indices if i != s.index]
            lines.append(f"- **Redundancy ({r.issue})** — overlaps with slides "
                         f"{', '.join(str(i) for i in others) or '(self-cluster)'}: {r.summary}")
            lines.append(f"  - Fix: {r.rewrite}")
        lines.append("")

    lines.append("---")
    lines.append(f"_Cost: {actual_cost_summary}_")
    return "\n".join(lines)
