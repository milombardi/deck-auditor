"""Streamlit wrapper for the deck auditor.

The audit logic in voice.py / narrative.py / takeaway.py / redundancy.py /
density.py / scoring.py / report.py / extractor.py / cost.py is unchanged.
This file is a UI on top of those functions.
"""

import os
import tempfile
import time
from pathlib import Path

import streamlit as st
from anthropic import Anthropic

import config
import density
import narrative
import redundancy
import report as report_mod
import scoring
import takeaway
import voice
from cost import CostTracker, estimate
from extractor import extract


# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Deck Auditor",
    page_icon="🎯",
    layout="centered",
    menu_items={"Get help": None, "Report a bug": None, "About": None},
)

# Hide Streamlit chrome + apply clean theme.
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    /* Hide everything we can of the Streamlit chrome. */
    #MainMenu,
    header[data-testid="stHeader"],
    footer,
    .stAppDeployButton,
    [data-testid="stToolbar"],
    [data-testid="stStatusWidget"],
    [data-testid="stDecoration"] {
        visibility: hidden !important;
        height: 0 !important;
        padding: 0 !important;
        margin: 0 !important;
    }

    /* Inter for the page text. Scope narrowly so we don't override the
       Material Symbols icon font used by Streamlit's chevrons, drag handles,
       etc. (overriding that font causes the raw ligature name like
       "arrow_drop_down" to show through as literal text). */
    html, body, .stApp,
    .stApp p, .stApp li, .stApp label, .stApp span:not([class*="material"]):not([data-testid*="Icon"]),
    .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6,
    .stApp button, .stApp input, .stApp textarea, .stApp select,
    [data-testid="stMarkdownContainer"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }

    /* Preserve icon fonts. */
    [class*="material-symbols"],
    [class*="material-icons"],
    [data-testid*="Icon"] svg,
    [data-testid="stExpanderToggleIcon"],
    [data-testid="stIconMaterial"] {
        font-family: 'Material Symbols Rounded', 'Material Icons' !important;
    }

    /* Off-white canvas. */
    .stApp { background: #fafafa; }

    /* Tighter, more breathable container. */
    .block-container {
        padding-top: 3rem !important;
        padding-bottom: 4rem !important;
        max-width: 720px !important;
    }

    /* Hero */
    .da-hero h1 {
        font-family: 'Inter', sans-serif !important;
        font-weight: 800 !important;
        font-size: 2.75rem !important;
        line-height: 1.1 !important;
        letter-spacing: -0.025em;
        color: #0f172a;
        margin: 0 0 0.5rem 0 !important;
    }
    .da-hero p {
        color: #64748b;
        font-size: 1.05rem;
        line-height: 1.55;
        margin: 0 0 0 0 !important;
        max-width: 36rem;
    }

    /* Thin divider used between major sections. */
    .da-divider {
        border: none;
        border-top: 1px solid #e2e8f0;
        margin: 2.25rem 0;
    }

    /* Section subheaders */
    .stApp h3, .stApp h2 {
        font-weight: 700 !important;
        color: #0f172a;
        letter-spacing: -0.01em;
    }

    /* Inputs */
    .stTextInput input, .stNumberInput input, .stFileUploader section {
        border-radius: 8px !important;
        border: 1px solid #e2e8f0 !important;
        background: #ffffff !important;
    }
    .stTextInput input:focus, .stNumberInput input:focus {
        border-color: #2563eb !important;
        box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12) !important;
    }

    /* Buttons */
    div.stButton > button, div.stDownloadButton > button {
        border-radius: 8px !important;
        padding: 0.55rem 1.4rem !important;
        font-weight: 600 !important;
        border: 1px solid transparent !important;
        transition: all 0.15s ease !important;
    }
    div.stButton > button[kind="primary"],
    div.stDownloadButton > button {
        background: #2563eb !important;
        color: #ffffff !important;
    }
    div.stButton > button[kind="primary"]:hover:not([disabled]),
    div.stDownloadButton > button:hover {
        background: #1d4ed8 !important;
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.22) !important;
        transform: translateY(-1px);
    }
    div.stButton > button[disabled] {
        background: #e2e8f0 !important;
        color: #94a3b8 !important;
    }
    div.stButton > button:not([kind="primary"]) {
        background: #ffffff !important;
        color: #0f172a !important;
        border: 1px solid #e2e8f0 !important;
    }

    /* Expanders */
    .streamlit-expanderHeader, [data-testid="stExpander"] summary {
        font-weight: 600 !important;
        color: #0f172a !important;
    }
    [data-testid="stExpander"] {
        border: 1px solid #e2e8f0 !important;
        border-radius: 10px !important;
        background: #ffffff !important;
    }

    /* Metric cards */
    [data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 0.75rem 1rem;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.8rem !important;
        color: #64748b !important;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }
    [data-testid="stMetricValue"] {
        font-weight: 700 !important;
        color: #0f172a !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="da-hero">
      <h1>Deck Auditor</h1>
      <p>Audits PowerPoint decks for narrative quality, AI voice, density, and clarity.</p>
    </div>
    <hr class="da-divider" />
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "api_key" not in st.session_state:
    st.session_state.api_key = ""
if "pending_high_cost" not in st.session_state:
    st.session_state.pending_high_cost = None  # holds Estimate if confirm needed


# ---------------------------------------------------------------------------
# Password gate
# ---------------------------------------------------------------------------

def _check_password():
    try:
        expected = st.secrets["APP_PASSWORD"]
    except (KeyError, FileNotFoundError):
        st.error("Server misconfigured: APP_PASSWORD is not set in secrets.")
        st.stop()

    if st.session_state.authenticated:
        return True

    pw = st.text_input("Password", type="password", key="_pw_input")
    if st.button("Sign in", type="primary", disabled=not pw):
        if pw == expected:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    return False


if not _check_password():
    st.stop()


# ---------------------------------------------------------------------------
# API key
# ---------------------------------------------------------------------------

st.subheader("Your API key")
api_key = st.text_input(
    "Your Anthropic API key (required)",
    type="password",
    value=st.session_state.api_key,
    help="Get one at console.anthropic.com. Used only for your audits. Never stored or logged.",
)
if api_key:
    st.session_state.api_key = api_key

key_valid = api_key.startswith("sk-ant-") if api_key else False
if api_key and not key_valid:
    st.error("That doesn't look like an Anthropic API key. It should start with `sk-ant-`.")


# ---------------------------------------------------------------------------
# Audit inputs
# ---------------------------------------------------------------------------

st.subheader("Deck")
uploaded = st.file_uploader("Upload a .pptx file", type=["pptx"])

col1, col2 = st.columns(2)
with col1:
    meeting_minutes = st.number_input(
        "Meeting length (minutes)", min_value=1, max_value=600,
        value=config.DEFAULT_MEETING_MINUTES, step=5,
    )
with col2:
    max_cost = st.number_input(
        "Max cost ($)", min_value=0.10, max_value=100.0,
        value=float(config.DEFAULT_MAX_COST), step=0.50, format="%.2f",
    )

ready = key_valid and uploaded is not None
run_clicked = st.button("Run Audit", type="primary", disabled=not ready)


# ---------------------------------------------------------------------------
# Audit pipeline
# ---------------------------------------------------------------------------

def _band_color(band: str) -> str:
    return {
        "ready": "#16a34a",       # green
        "close": "#2563eb",       # blue
        "needs work": "#ca8a04",  # yellow
        "rebuild": "#dc2626",     # red
    }.get(band, "#6b7280")


def _seconds_estimate(n_slides: int) -> int:
    # ~4s per slide across voice + narrative + takeaway + a single redundancy call.
    return max(15, int(n_slides * 4))


def _run_audit(deck_bytes: bytes, deck_name: str, api_key: str,
               meeting_minutes: int):
    """Runs the full audit pipeline. Returns a dict with results."""
    # python-pptx works best with a path; write a temp file we control.
    with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as tmp:
        tmp.write(deck_bytes)
        tmp_path = tmp.name

    try:
        slides = extract(tmp_path)
        if not slides:
            raise RuntimeError("No slides found in deck.")

        client = Anthropic(api_key=api_key)
        tracker = CostTracker()

        # Each check function uses the same client/tracker pattern as the CLI.
        voice_results = {
            "regex": voice.regex_scan(slides),
            "deck_construction": voice.deck_construction_scan(slides),
            "api": voice.api_scan(slides, client, tracker),
        }
        density_flags = density.run(slides, meeting_minutes)
        headline_flags = narrative.run(slides, client, tracker)
        takeaway_flags = takeaway.run(slides, client, tracker)
        redundancy_flags = redundancy.run(slides, client, tracker)

        scores = scoring.score(
            slides, headline_flags, takeaway_flags,
            voice_results, density_flags, redundancy_flags,
        )
        report_md = report_mod.build(
            deck_path=deck_name,
            slides=slides,
            scores=scores,
            headline_flags=headline_flags,
            takeaway_flags=takeaway_flags,
            voice_flags=voice_results,
            density_flags=density_flags,
            redundancy_flags=redundancy_flags,
            actual_cost_summary=tracker.summary(),
        )

        return {
            "slides": slides,
            "scores": scores,
            "headline_flags": headline_flags,
            "takeaway_flags": takeaway_flags,
            "voice_flags": voice_results,
            "density_flags": density_flags,
            "redundancy_flags": redundancy_flags,
            "report_md": report_md,
            "cost_summary": tracker.summary(),
            "cost": tracker.cost,
        }
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _execute_and_render(deck_bytes: bytes, deck_name: str, n_slides: int):
    est_secs = _seconds_estimate(n_slides)
    spinner_msg = f"Analyzing {n_slides} slides, about {est_secs} seconds."
    start = time.time()
    with st.spinner(spinner_msg):
        results = _run_audit(
            deck_bytes=deck_bytes,
            deck_name=deck_name,
            api_key=st.session_state.api_key,
            meeting_minutes=int(meeting_minutes),
        )
    elapsed = time.time() - start
    _render_results(results, deck_name, elapsed)


def _render_results(results: dict, deck_name: str, elapsed: float):
    scores = results["scores"]
    band = scores.band
    color = _band_color(band)

    st.markdown(
        f"<div style='margin: 1rem 0;'>"
        f"<div style='font-size: 4rem; font-weight: 800; color: {color}; line-height: 1;'>"
        f"{scores.total}<span style='font-size: 2rem; color: #6b7280;'>/100</span>"
        f"</div>"
        f"<div style='font-size: 1.5rem; font-weight: 600; color: {color}; "
        f"text-transform: uppercase; letter-spacing: 0.05em;'>{band}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Narrative", f"{scores.narrative}/20")
    c2.metric("Takeaway", f"{scores.takeaway}/20")
    c3.metric("Voice", f"{scores.voice}/20")
    c4.metric("Density", f"{scores.density}/20")
    c5.metric("Redundancy", f"{scores.redundancy}/20")

    md = results["report_md"]

    # Sections of the report split by H2 for clean expanders.
    sections = _split_report(md)

    with st.expander("Top 5 Fixes", expanded=True):
        st.markdown(sections.get("Top 5 fixes", "_None._"))

    with st.expander("Deck-Level Findings"):
        st.markdown(sections.get("Deck-level findings", "_None._"))

    with st.expander("Slide-by-Slide Detail"):
        st.markdown(sections.get("Slide-by-slide", "_None._"))

    base = Path(deck_name).stem
    st.download_button(
        "Download full markdown report",
        data=md,
        file_name=f"{base}-audit.md",
        mime="text/markdown",
    )

    st.caption(
        f"Run cost: {results['cost_summary']} · "
        f"Elapsed: {elapsed:.1f}s"
    )


def _split_report(md: str) -> dict:
    """Split the report by '## ' headers. Returns a {section_title: body} dict."""
    out = {}
    current = None
    buf = []
    for line in md.splitlines():
        if line.startswith("## "):
            if current is not None:
                out[current] = "\n".join(buf).strip()
            current = line[3:].strip()
            buf = []
        else:
            if current is not None:
                buf.append(line)
    if current is not None:
        out[current] = "\n".join(buf).strip()
    return out


# ---------------------------------------------------------------------------
# Run flow with cost guardrail
# ---------------------------------------------------------------------------

if run_clicked or st.session_state.pending_high_cost is not None:
    if uploaded is None:
        st.error("Upload a .pptx file first.")
        st.stop()

    deck_bytes = uploaded.getvalue()
    deck_name = uploaded.name

    # Quick estimate without API calls.
    with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as tmp:
        tmp.write(deck_bytes)
        tmp_path = tmp.name
    try:
        slides = extract(tmp_path)
    finally:
        os.unlink(tmp_path)

    est = estimate(slides)

    if len(slides) > config.SLIDE_HARD_STOP:
        st.error(
            f"Deck has {len(slides)} slides, above the hard stop "
            f"({config.SLIDE_HARD_STOP}). Trim the deck and try again."
        )
        st.session_state.pending_high_cost = None
        st.stop()

    if len(slides) > config.SLIDE_WARN:
        st.warning(
            f"{len(slides)} slides is a lot. This will be slow and may be costly."
        )

    # Cost gate
    if est.cost > max_cost and st.session_state.pending_high_cost is None:
        st.session_state.pending_high_cost = {
            "deck_bytes": deck_bytes,
            "deck_name": deck_name,
            "n_slides": len(slides),
            "est_cost": est.cost,
        }
        st.rerun()

    if st.session_state.pending_high_cost is not None:
        p = st.session_state.pending_high_cost
        st.warning(
            f"Estimated cost is ${p['est_cost']:.2f}, above your cap of "
            f"${max_cost:.2f}. Confirm to proceed."
        )
        c_ok, c_cancel = st.columns(2)
        if c_ok.button("Confirm and run", type="primary"):
            data = st.session_state.pending_high_cost
            st.session_state.pending_high_cost = None
            _execute_and_render(data["deck_bytes"], data["deck_name"], data["n_slides"])
            st.stop()
        if c_cancel.button("Cancel"):
            st.session_state.pending_high_cost = None
            st.rerun()
        st.stop()

    # Under the cap — run directly.
    _execute_and_render(deck_bytes, deck_name, len(slides))
