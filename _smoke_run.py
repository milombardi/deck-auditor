"""Smoke test: drive _run_audit() the same way the Streamlit app does.

This exercises the upload-to-report path end-to-end without the browser file picker.
"""
import os
import sys
import time

# Re-use the same helper the Streamlit app uses.
from app import _run_audit

API_KEY = os.environ["ANTHROPIC_API_KEY"]
DECK_PATH = "/Users/michael.lombardi/Downloads/031926_Tax Naming Reco_ml.pptx"

with open(DECK_PATH, "rb") as f:
    deck_bytes = f.read()

t0 = time.time()
results = _run_audit(
    deck_bytes=deck_bytes,
    deck_name=os.path.basename(DECK_PATH),
    api_key=API_KEY,
    meeting_minutes=30,
)
elapsed = time.time() - t0

s = results["scores"]
print("---")
print(f"score: {s.total}/100 — {s.band}")
print(f"  narrative={s.narrative} takeaway={s.takeaway} voice={s.voice} "
      f"density={s.density} redundancy={s.redundancy}")
print(f"report length: {len(results['report_md'])} chars")
print(f"cost: {results['cost_summary']}")
print(f"elapsed: {elapsed:.1f}s")
print("first 200 chars of report:")
print(results["report_md"][:200])
