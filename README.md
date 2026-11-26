# Ghost Job & Scam Detector

Standalone web application and explainable detection engine to identify fake job postings, recruitment scams, and passive ghost jobs from major job portals.

Created by [radja973](https://github.com/radja973).

## Key Features

- **Multi-Portal URL Scanner**: Dedicated URL fields with strict domain validation for **LinkedIn**, **Glints**, **Indeed Jobs**, **Upwork**, **Dealls**, plus **JobStreet / Kalibrr / Glassdoor / Others** and expandable custom URL inputs.
- **Automated Metadata Extraction**: Parses JSON-LD, portal DOM structures, and OpenGraph metadata to extract job title, company name, posting age, contact email, and description, while flagging anti-bot walls (`UNVERIFIED`) and expired pages (`404 / Page Not Found`).
- **Explainable Trust Score (0-100)**:
  - `80-100` (`SAFE`): Appears legitimate.
  - `50-79` (`GHOST_OR_CAUTION`): Caution / possible ghost job (e.g., open >= 30 or >= 45 days, missing company, vague description, contradictory experience requirements).
  - `0-49` (`HIGH_RISK_SCAM`): High risk / likely scam (upfront fee requests, unofficial Telegram/WhatsApp interviews, unrealistic salary claims, free email on corporate entities).
- **Bilingual UI (ID / EN)**: Instant Indonesian and English switching across the entire interface.
- **Scan History & Ghost Job List**: Persistent local scan history (`scan_history.csv` with `localStorage` fallback) with one-click rescan, plus a saved Ghost Job list (`ghost_jobs.csv`).
- **Manual Fallback Mode**: Paste job details manually if a portal blocks automated scraping.

## Quick Start

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Run the server:
   - Windows: double-click `run_detector.bat`
   - Linux/macOS: `./run_detector.sh`
   - Or manually: `uvicorn app:app --host 127.0.0.1 --port 8010`
3. Open `http://localhost:8010` in your browser.

## Running Tests

```bash
python -m unittest discover -s tests -v
```
