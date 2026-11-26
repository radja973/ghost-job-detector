import json
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import lxml.html
import requests

from .engine import extract_emails

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
}

PORTAL_MAP = (
    ("linkedin.com", "LinkedIn"),
    ("glints.com", "Glints"),
    ("indeed.com", "Indeed"),
    ("upwork.com", "Upwork"),
    ("dealls.com", "Dealls"),
    ("jobstreet.", "JobStreet"),
    ("kalibrr.com", "Kalibrr"),
    ("glassdoor.", "Glassdoor"),
    ("karir.com", "Karir"),
    ("techinasia.com", "Tech in Asia"),
    ("loker.id", "Loker.id"),
    ("cake.me", "Cake"),
)


def detect_portal(url: str) -> str:
    host = urlparse(url).netloc.lower()
    for domain_part, label in PORTAL_MAP:
        if domain_part in host:
            return label
    return host.replace("www.", "") or "Other"


def normalize_job_url(url: str) -> str:
    clean = (url or "").strip()
    if not clean:
        return ""
    if not clean.startswith(("http://", "https://")):
        clean = "https://" + clean
    parsed = urlparse(clean)
    if "linkedin.com" in parsed.netloc.lower():
        qs = parse_qs(parsed.query)
        if "currentJobId" in qs and qs["currentJobId"]:
            job_id = re.sub(r"\D", "", qs["currentJobId"][0])
            if job_id:
                return f"https://www.linkedin.com/jobs/view/{job_id}/"
    return clean


def _strip_html(raw_html: str) -> str:
    if not raw_html:
        return ""
    try:
        doc = lxml.html.fromstring(raw_html)
        text = doc.text_content()
    except Exception:
        text = re.sub(r"<[^>]+>", " ", raw_html)
    return re.sub(r"\s+", " ", text).strip()


def parse_posting_age_days(text: str) -> int | None:
    if not text:
        return None
    low = text.strip().lower()

    if any(k in low for k in ("today", "just now", "hari ini", "baru saja", "hour", "jam", "minute", "menit")):
        return 0

    m_month = re.search(r"(\d+)\s*\+?\s*(?:months?|mos?|bulan|bln)\b", low)
    if m_month:
        return int(m_month.group(1)) * 30

    m_week = re.search(r"(\d+)\s*\+?\s*(?:weeks?|wks?|minggu|mgg)\b", low)
    if m_week:
        return int(m_week.group(1)) * 7

    m_day = re.search(r"(\d+)\s*\+?\s*(?:days?|hari)\b", low)
    if m_day:
        return int(m_day.group(1))

    m_iso = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if m_iso:
        try:
            dt = datetime.strptime(m_iso.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
            delta = (datetime.now(timezone.utc) - dt).days
            return max(0, delta)
        except ValueError:
            pass
    return None


def _extract_from_json_ld(doc) -> dict:
    out = {}
    for script in doc.xpath('//script[@type="application/ld+json"]'):
        raw = (script.text_content() or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            if "@graph" in item and isinstance(item["@graph"], list):
                items.extend(item["@graph"])
                continue
            item_type = str(item.get("@type", "")).lower()
            if "jobposting" in item_type or ("title" in item and "hiringOrganization" in item):
                out["title"] = str(item.get("title") or "").strip()
                org = item.get("hiringOrganization")
                if isinstance(org, dict):
                    out["company"] = str(org.get("name") or "").strip()
                elif isinstance(org, str):
                    out["company"] = org.strip()
                out["description"] = _strip_html(str(item.get("description") or ""))
                date_posted = str(item.get("datePosted") or "")
                out["posting_age_days"] = parse_posting_age_days(date_posted)
                return out
    return out


def _split_page_title(page_title: str) -> tuple[str, str]:
    if not page_title:
        return "", ""
    cleaned = re.sub(
        r"\s*\|\s*(?:LinkedIn Jobs|LinkedIn|Glints|Indeed(?:\.com)?|Upwork|Dealls|JobStreet|Kalibrr|Glassdoor).*$",
        "",
        page_title,
        flags=re.IGNORECASE,
    ).strip()
    # Pattern: "Role at Company — Location"
    m_at = re.match(r"^(.+?)\s+at\s+([^—\-|]+)", cleaned, re.IGNORECASE)
    if m_at:
        return m_at.group(1).strip(), m_at.group(2).strip()
    # Pattern: "Role - Company - Location"
    parts = [p.strip() for p in re.split(r"\s+[-—]\s+", cleaned) if p.strip()]
    if len(parts) >= 2:
        return parts[0], parts[1]
    return cleaned, ""


def _first_xpath_text(doc, xpaths: list[str]) -> str:
    for xp in xpaths:
        nodes = doc.xpath(xp)
        if nodes:
            raw = nodes[0].text_content() if hasattr(nodes[0], "text_content") else str(nodes[0])
            txt = re.sub(r"\s+", " ", raw).strip()
            if txt:
                return txt
    return ""


def parse_job_html(html: str, url: str = "") -> dict:
    portal = detect_portal(url) if url else "Other"
    if not html or not html.strip():
        return {
            "portal": portal,
            "title": "",
            "company": "",
            "description": "",
            "posting_age_days": None,
            "contact_email": "",
        }

    doc = lxml.html.fromstring(html)
    ld = _extract_from_json_ld(doc)

    title = ld.get("title", "")
    company = ld.get("company", "")
    description = ld.get("description", "")
    posting_age_days = ld.get("posting_age_days")

    # Portal-specific & general DOM selectors
    if not title:
        title = _first_xpath_text(doc, [
            '//h1[contains(@class,"top-card-layout__title")]',
            '//h1[contains(@class,"jobsearch-JobInfoHeader-title")]',
            '//h1',
        ])

    if not company:
        company = _first_xpath_text(doc, [
            '//*[contains(@class,"topcard__org-name-link")]',
            '//*[contains(@class,"top-card-layout__second-subline")]//a',
            '//*[@data-company-name="true"]',
            '//*[@data-testid="inlineHeader-companyName"]',
            '//*[contains(@class,"company-name")]',
        ])

    if not description:
        description = _first_xpath_text(doc, [
            '//*[contains(@class,"show-more-less-html__markup")]',
            '//*[@id="jobDescriptionText"]',
            '//*[contains(@class,"job-description")]',
            '//article',
        ])

    if posting_age_days is None:
        age_text = _first_xpath_text(doc, [
            '//*[contains(@class,"posted-time-ago__text")]',
            '//*[contains(@class,"posted-time-ago")]',
            '//*[contains(@class,"job-age")]',
            '//time',
        ])
        posting_age_days = parse_posting_age_days(age_text)
        if posting_age_days is None:
            # Scan visible body text snippet for relative age phrases
            body_txt = _first_xpath_text(doc, ['//main', '//body'])[:2500]
            posting_age_days = parse_posting_age_days(body_txt)

    # Meta / <title> fallback
    og_title = _first_xpath_text(doc, ['//meta[@property="og:title"]/@content'])
    if not og_title:
        nodes = doc.xpath('//meta[@property="og:title"]/@content')
        og_title = str(nodes[0]).strip() if nodes else ""
    page_title = _first_xpath_text(doc, ['//title'])

    if not title or not company:
        t_split, c_split = _split_page_title(og_title or page_title)
        if not title:
            title = t_split
        if not company:
            company = c_split

    if not description:
        meta_desc = doc.xpath('//meta[@name="description"]/@content | //meta[@property="og:description"]/@content')
        if meta_desc:
            description = str(meta_desc[0]).strip()

    emails = extract_emails(description)
    contact_email = emails[0] if emails else ""

    return {
        "portal": portal,
        "title": title,
        "company": company,
        "description": description,
        "posting_age_days": posting_age_days,
        "contact_email": contact_email,
    }


def fetch_and_extract_job(url: str, timeout: int = 12) -> dict:
    normalized = normalize_job_url(url)
    portal = detect_portal(normalized)
    if not normalized:
        return {
            "url": url,
            "normalized_url": "",
            "portal": portal,
            "fetch_status": "error",
            "fetch_message_id": "URL tidak boleh kosong.",
            "fetch_message_en": "URL cannot be empty.",
            "title": "",
            "company": "",
            "description": "",
            "posting_age_days": None,
            "contact_email": "",
        }

    try:
        resp = requests.get(normalized, headers=DEFAULT_HEADERS, timeout=timeout, allow_redirects=True)
        html = resp.text or ""
        low_html = html.lower()

        is_challenge = (
            resp.status_code in (403, 429, 999)
            or "just a moment" in low_html
            or "cf-browser-verification" in low_html
            or "enable javascript and cookies to continue" in low_html
        )

        extracted = parse_job_html(html, normalized)
        low_title = (extracted.get("title") or "").strip().lower()
        is_challenge_title = any(
            marker in low_title
            for marker in ("just a moment", "attention required", "access denied", "cloudflare", "captcha")
        )
        is_not_found_title = any(
            marker in low_title
            for marker in ("page not found", "404", "job not found", "lowongan tidak ditemukan")
        )

        if is_challenge or is_challenge_title:
            return {
                "url": url,
                "normalized_url": normalized,
                "portal": portal,
                "fetch_status": "blocked",
                "fetch_message_id": f"{portal} membatasi akses otomatis (proteksi anti-bot / HTTP {resp.status_code}). Gunakan Mode Manual di bawah.",
                "fetch_message_en": f"{portal} blocked automated access (anti-bot / HTTP {resp.status_code}). Use Manual Mode below.",
                "title": "",
                "company": "",
                "description": "",
                "posting_age_days": None,
                "contact_email": "",
            }

        if is_not_found_title:
            return {
                "url": url,
                "normalized_url": normalized,
                "portal": portal,
                "fetch_status": "error",
                "fetch_message_id": f"Halaman lowongan di {portal} tidak ditemukan / sudah kedaluwarsa (404 / Page Not Found).",
                "fetch_message_en": f"Job page on {portal} was not found or has expired (404 / Page Not Found).",
                "title": "",
                "company": "",
                "description": "",
                "posting_age_days": None,
                "contact_email": "",
            }

        has_useful_data = bool(extracted["title"] or extracted["company"] or len(extracted["description"]) > 40)

        if resp.status_code >= 400 and not has_useful_data:
            return {
                "url": url,
                "normalized_url": normalized,
                "portal": portal,
                "fetch_status": "error",
                "fetch_message_id": (
                    f"{portal} gagal diakses (HTTP {resp.status_code}). Coba tempel deskripsi di Mode Manual."
                ),
                "fetch_message_en": (
                    f"{portal} failed to load (HTTP {resp.status_code}). Try pasting the description in Manual Mode."
                ),
                **extracted,
            }

        return {
            "url": url,
            "normalized_url": normalized,
            "portal": portal,
            "fetch_status": "ok",
            "fetch_message_id": f"Berhasil mengambil data dari {portal}.",
            "fetch_message_en": f"Successfully fetched listing from {portal}.",
            **extracted,
        }
    except Exception as exc:
        return {
            "url": url,
            "normalized_url": normalized,
            "portal": portal,
            "fetch_status": "error",
            "fetch_message_id": f"Gagal mengakses {portal}: {exc}",
            "fetch_message_en": f"Failed to reach {portal}: {exc}",
            "title": "",
            "company": "",
            "description": "",
            "posting_age_days": None,
            "contact_email": "",
        }
