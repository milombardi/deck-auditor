# Deck Auditor

Audits PowerPoint decks for narrative quality, AI voice, density, and clarity.
Two ways to run it: a CLI (`audit.py`) and a Streamlit web app (`app.py`).

## Local testing

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Set a local password in `.streamlit/secrets.toml` (a placeholder `APP_PASSWORD = "test"` is included).

Run the app:

```bash
streamlit run app.py
```

Open the URL Streamlit prints (usually `http://localhost:8501`).

1. Enter the password from `secrets.toml`.
2. Paste your Anthropic API key (must start with `sk-ant-`). It's held in session
   memory only — never written to disk or logs.
3. Upload a `.pptx`, set meeting length and max cost, click **Run Audit**.

## CLI usage

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python audit.py path/to/deck.pptx [--meeting-minutes 30] [--max-cost 3] \
    [--hard-cap 10] [--force] [--dry-run]
```

The CLI writes the report next to the input file as `<deck>-audit.md`.

## Files

- `app.py` — Streamlit UI
- `audit.py` — CLI entry point
- `config.py` — model name, pricing, thresholds, voice word lists
- `extractor.py`, `voice.py`, `narrative.py`, `takeaway.py`, `density.py`,
  `redundancy.py`, `scoring.py`, `report.py` — audit logic

## Deployment

_To be filled in._ Likely targets:

- Streamlit Community Cloud — set `APP_PASSWORD` as a secret in the app settings.
- A small container (Dockerfile TBD) on Fly.io / Render / Cloud Run with
  `APP_PASSWORD` injected via the platform's secret manager.

Whatever you pick, never commit `.streamlit/secrets.toml` with a real password.
