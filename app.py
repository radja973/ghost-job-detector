import csv
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

from detector import analyze_job_posting, fetch_and_extract_job

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
GHOST_JOBS_CSV = os.path.join(BASE_DIR, "ghost_jobs.csv")
SCAN_HISTORY_CSV = os.path.join(BASE_DIR, "scan_history.csv")
_HISTORY_LOCK = threading.Lock()

app = FastAPI(title="Ghost Job & Scam Detector")


class AnalyzeRequest(BaseModel):
    title: str = ""
    company: str = ""
    description: str = ""
    contact_email: str = ""
    posting_age_days: int | None = None
    job_url: str = ""
    check_dns: bool = False


class AnalyzeUrlsRequest(BaseModel):
    urls: list[str] = []
    check_dns: bool = False


class ReportRequest(BaseModel):
    job_url: str = ""
    title: str = ""
    company: str = ""
    note: str = ""


def _analyze_single_url(url: str, check_dns: bool = False) -> dict:
    fetched = fetch_and_extract_job(url)
    if fetched["fetch_status"] != "ok" and not (fetched["title"] or fetched["company"] or fetched["description"]):
        return {
            **fetched,
            "score": None,
            "category": "UNVERIFIED",
            "label_id": "Tidak Dapat Diambil Otomatis",
            "label_en": "Could Not Fetch Automatically",
            "reasons": [],
        }

    analysis = analyze_job_posting(
        title=fetched["title"],
        company=fetched["company"],
        description=fetched["description"],
        contact_email=fetched["contact_email"],
        posting_age_days=fetched["posting_age_days"],
        job_url=fetched["normalized_url"] or url,
        check_dns=check_dns,
    )
    return {
        **fetched,
        **analysis,
    }


def _append_history(items: list[dict]):
    if not items:
        return
    with _HISTORY_LOCK:
        exists = os.path.exists(SCAN_HISTORY_CSV)
        with open(SCAN_HISTORY_CSV, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if not exists:
                w.writerow(["Timestamp", "Portal", "Job Title", "Company", "Job URL", "Score", "Category", "Fetch Status"])
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for it in items:
                w.writerow([
                    now_str,
                    it.get("portal", "Manual"),
                    (it.get("title") or "").strip(),
                    (it.get("company") or "").strip(),
                    (it.get("normalized_url") or it.get("url") or "").strip(),
                    "" if it.get("score") is None else it.get("score"),
                    it.get("category", ""),
                    it.get("fetch_status", "ok"),
                ])


@app.get("/")
def serve_home():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.post("/api/analyze")
def api_analyze(req: AnalyzeRequest):
    if req.job_url.strip() and not (req.title.strip() or req.company.strip() or req.description.strip()):
        res = _analyze_single_url(req.job_url.strip(), check_dns=req.check_dns)
        _append_history([res])
        return res

    res = analyze_job_posting(
        title=req.title,
        company=req.company,
        description=req.description,
        contact_email=req.contact_email,
        posting_age_days=req.posting_age_days,
        job_url=req.job_url,
        check_dns=req.check_dns,
    )
    _append_history([{
        "portal": "Manual",
        "title": req.title,
        "company": req.company,
        "normalized_url": req.job_url,
        "fetch_status": "ok",
        **res,
    }])
    return res


@app.post("/api/analyze-urls")
def api_analyze_urls(req: AnalyzeUrlsRequest):
    clean_urls = [u.strip() for u in req.urls if u and u.strip()]
    if not clean_urls:
        return {"results": []}

    with ThreadPoolExecutor(max_workers=min(6, len(clean_urls))) as pool:
        results = list(pool.map(lambda u: _analyze_single_url(u, req.check_dns), clean_urls))
    _append_history(results)
    return {"results": results}


@app.get("/api/history")
def api_list_history():
    if not os.path.exists(SCAN_HISTORY_CSV):
        return {"items": []}
    with _HISTORY_LOCK:
        with open(SCAN_HISTORY_CSV, "r", newline="", encoding="utf-8") as f:
            items = list(csv.DictReader(f))
    items.reverse()
    return {"items": items[:50]}


@app.delete("/api/history")
def api_clear_history():
    with _HISTORY_LOCK:
        if os.path.exists(SCAN_HISTORY_CSV):
            os.remove(SCAN_HISTORY_CSV)
    return {"status": "ok"}


@app.get("/api/ghost-jobs")
def api_list_ghost_jobs():
    if not os.path.exists(GHOST_JOBS_CSV):
        return {"items": []}
    items = []
    with open(GHOST_JOBS_CSV, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            items.append(row)
    items.reverse()
    return {"items": items}


@app.post("/api/ghost-jobs")
@app.post("/api/report")
def api_add_ghost_job(req: ReportRequest):
    exists = os.path.exists(GHOST_JOBS_CSV)
    with open(GHOST_JOBS_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(["Timestamp", "Job Title", "Company", "Job URL", "Note"])
        w.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            req.title.strip(),
            req.company.strip(),
            req.job_url.strip(),
            req.note.strip(),
        ])
    return {"status": "ok"}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8010"))
    print("=" * 60)
    print("   GHOST JOB & SCAM DETECTOR by radja973")
    print("=" * 60)
    print(f" Open in browser: http://localhost:{port}")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
