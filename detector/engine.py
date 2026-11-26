import re
import socket

FREE_EMAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.id",
    "hotmail.com", "outlook.com", "live.com", "ymail.com", "proton.me", "protonmail.com"
}

SCAM_FEE_PATTERNS = [
    r"biaya\s+(?:admin|administrasi|pendaftaran|training|pelatihan|seragam|akomodasi|tes|medical)",
    r"(?:transfer|kirim|bayar)\s+(?:uang|dana|deposit|biaya|tiket)",
    r"rekening\s+pribadi",
    r"(?:upfront|registration|processing|training)\s+fee",
    r"(?:wire\s+transfer|pay\s+in\s+advance|security\s+deposit|buy\s+equipment)",
    r"reimburse\s*(?:tiket|ticket|travel|akomodasi)",
]

SCAM_CHANNEL_PATTERNS = [
    r"(?:interview|wawancara|seleksi|hubungi|chat)\s+(?:hanya\s+)?(?:via|melalui|lewat)\s+(?:telegram|wa\s+pribadi)",
    r"t\.me\/[a-zA-Z0-9_]+",
    r"(?:langsung\s+diterima|tanpa\s+interview|tanpa\s+wawancara|no\s+interview\s+required|instant\s+hiring)",
    r"(?:kerja\s+sampingan\s+like\s+follow|komisi\s+harian\s+jutaan)",
]

VAGUE_OR_HYPE_PATTERNS = [
    r"(?:gaji|penghasilan|income)\s+(?:hingga|up\s+to)?\s*(?:rp\s*)?(?:50|100)\s*juta",
    r"(?:earn|make)\s+\$\d{3,4}\s*(?:per\s+day|daily|a\s+day)",
    r"(?:no\s+experience\s+needed.*high\s+salary|tanpa\s+pengalaman.*gaji\s+tinggi)",
]


def extract_emails(text: str) -> list[str]:
    if not text:
        return []
    found = re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text)
    unique = []
    for em in found:
        low = em.lower().strip(".,;:)")
        if low not in unique and not any(low.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".gif")):
            unique.append(low)
    return unique


def _check_domain_resolves(domain: str) -> bool:
    try:
        socket.getaddrinfo(domain, None, proto=socket.IPPROTO_TCP)
        return True
    except Exception:
        return False


def _add_reason(reasons, code, points, title_id, title_en, detail_id, detail_en):
    reasons.append({
        "code": code,
        "points": points,
        "title_id": title_id,
        "title_en": title_en,
        "detail_id": detail_id,
        "detail_en": detail_en,
    })


def analyze_job_posting(
    title: str = "",
    company: str = "",
    description: str = "",
    contact_email: str = "",
    posting_age_days: int | None = None,
    job_url: str = "",
    check_dns: bool = False,
) -> dict:
    """
    Menganalisis keaslian lowongan kerja dan mendeteksi indikasi Ghost Job atau Penipuan.
    Mengembalikan skor kepercayaan (0-100), kategori risiko, dan daftar alasan (Explainable AI).
    """
    score = 100
    reasons = []

    title_clean = (title or "").strip()
    company_clean = (company or "").strip()
    desc_clean = (description or "").strip()
    combined_text = f"{title_clean}\n{company_clean}\n{desc_clean}".lower()

    # 1. Ekstrak email dari input maupun deskripsi
    extracted_emails = extract_emails(f"{contact_email} {desc_clean}")
    primary_email = (contact_email or "").strip().lower() or (extracted_emails[0] if extracted_emails else "")

    # 2. Cek pola penipuan biaya / transfer (Risiko Tinggi)
    fee_hits = [pat for pat in SCAM_FEE_PATTERNS if re.search(pat, combined_text, re.IGNORECASE)]
    if fee_hits:
        deduction = 45
        score -= deduction
        _add_reason(
            reasons, "UPFRONT_FEE", -deduction,
            "Indikasi Permintaan Biaya / Transfer",
            "Upfront Fee or Transfer Request Detected",
            "Deskripsi menyebutkan biaya administrasi, deposit, training berbayar, atau penggantian tiket.",
            "Description mentions administrative fees, deposits, paid training, or travel reimbursement.",
        )

    # 3. Cek kanal wawancara tidak resmi / janji lolos instan
    chan_hits = [pat for pat in SCAM_CHANNEL_PATTERNS if re.search(pat, combined_text, re.IGNORECASE)]
    if chan_hits:
        deduction = 30
        score -= deduction
        _add_reason(
            reasons, "UNOFFICIAL_CHANNEL", -deduction,
            "Kanal Seleksi Tidak Resmi / Instan",
            "Unofficial Channel or Instant Hiring Claim",
            "Mengarahkan wawancara lewat Telegram/WA pribadi atau menjanjikan diterima tanpa seleksi.",
            "Directs interviews to personal Telegram/WhatsApp or promises instant hiring without screening.",
        )

    # 4. Cek klaim gaji tidak masuk akal
    hype_hits = [pat for pat in VAGUE_OR_HYPE_PATTERNS if re.search(pat, combined_text, re.IGNORECASE)]
    if hype_hits:
        deduction = 20
        score -= deduction
        _add_reason(
            reasons, "UNREALISTIC_PAY", -deduction,
            "Klaim Penghasilan Tidak Wajar",
            "Unrealistic Salary Claim",
            "Menawarkan penghasilan sangat tinggi yang tidak sebanding dengan kualifikasi dasar.",
            "Promises unusually high income inconsistent with entry-level requirements.",
        )

    # 5. Verifikasi Email HRD vs Identitas Perusahaan
    if primary_email and "@" in primary_email:
        domain = primary_email.split("@")[-1].lower()
        is_free_mail = domain in FREE_EMAIL_DOMAINS
        looks_corporate = any(
            marker in company_clean.lower()
            for marker in ("pt ", "pt.", "tbk", "inc", "corp", "ltd", "group", "bank", "persero")
        )
        if is_free_mail and looks_corporate:
            deduction = 25
            score -= deduction
            _add_reason(
                reasons, "FREE_EMAIL_CORPORATE", -deduction,
                "Perusahaan Berbadan Hukum Memakai Email Gratis",
                "Corporate Entity Using Free Email Provider",
                f"Perusahaan '{company_clean}' mencantumkan email gratisan ({primary_email}) alih-alih domain resmi.",
                f"Company '{company_clean}' uses a free email ({primary_email}) instead of an official corporate domain.",
            )
        elif is_free_mail:
            deduction = 10
            score -= deduction
            _add_reason(
                reasons, "FREE_EMAIL_GENERIC", -deduction,
                "Kontak Menggunakan Email Gratis",
                "Contact Uses Free Email Domain",
                f"Email kontak ({primary_email}) menggunakan penyedia gratis; pastikan keaslian rekruter.",
                f"Contact email ({primary_email}) uses a free provider; verify recruiter authenticity.",
            )
        elif check_dns and not _check_domain_resolves(domain):
            deduction = 25
            score -= deduction
            _add_reason(
                reasons, "DEAD_EMAIL_DOMAIN", -deduction,
                "Domain Email Tidak Aktif",
                "Unreachable Email Domain",
                f"Domain email '{domain}' tidak dapat di-resolve melalui DNS.",
                f"Email domain '{domain}' could not be resolved via DNS.",
            )

    # 6. Deteksi Ghost Job: Umur postingan terlalu lama
    if posting_age_days is not None:
        if posting_age_days >= 45:
            deduction = 20
            score -= deduction
            _add_reason(
                reasons, "STALE_POSTING_45D", -deduction,
                f"Indikasi Ghost Job (Tayang {posting_age_days} Hari)",
                f"Ghost Job Signal (Active {posting_age_days} Days)",
                "Lowongan sudah tayang >= 45 hari; berisiko merupakan lowongan pasif / pengumpul CV.",
                "Listing has been open >= 45 days; high likelihood of a stale or pipeline-hoarding post.",
            )
        elif posting_age_days >= 30:
            deduction = 10
            score -= deduction
            _add_reason(
                reasons, "AGING_POSTING_30D", -deduction,
                f"Lowongan Sudah Cukup Lama ({posting_age_days} Hari)",
                f"Aging Job Listing ({posting_age_days} Days)",
                "Lowongan sudah aktif lebih dari 30 hari; periksa apakah posisi masih benar-benar dibuka.",
                "Listing has been active for over 30 days; verify whether hiring is still active.",
            )

    # 7. Deteksi Ghost Job: Profil perusahaan kosong / deskripsi sangat generik
    if not company_clean or company_clean.lower() in ("company", "perusahaan", "confidential", "rahasia"):
        deduction = 10
        score -= deduction
        _add_reason(
            reasons, "MISSING_COMPANY", -deduction,
            "Nama Perusahaan Tidak Jelas / Disembunyikan",
            "Missing or Obscured Company Name",
            "Tidak mencantumkan identitas perusahaan yang dapat diverifikasi.",
            "Company identity is missing or obscured, making verification difficult.",
        )

    word_count = len(desc_clean.split())
    if 0 < word_count < 35:
        deduction = 10
        score -= deduction
        _add_reason(
            reasons, "VAGUE_DESCRIPTION", -deduction,
            "Deskripsi Lowongan Terlalu Singkat / Generik",
            "Overly Brief or Generic Job Description",
            f"Deskripsi hanya {word_count} kata tanpa rincian tugas tim atau kualifikasi yang jelas.",
            f"Description is only {word_count} words without clear role responsibilities or team context.",
        )

    # 8. Deteksi Kontradiksi Persyaratan (misal Fresh Graduate tapi minta >= 5 tahun pengalaman)
    is_junior_title = any(k in title_clean.lower() for k in ("fresh graduate", "entry level", "intern", "magang", "junior"))
    exp_match = re.search(r"(\d+)\s*\+?\s*(?:years?|tahun)\s+(?:of\s+)?(?:experience|pengalaman)", combined_text)
    if is_junior_title and exp_match:
        req_years = int(exp_match.group(1))
        if req_years >= 5:
            deduction = 10
            score -= deduction
            _add_reason(
                reasons, "CONTRADICTORY_REQUIREMENT", -deduction,
                "Syarat Pengalaman Kontradiktif",
                "Contradictory Experience Requirement",
                f"Judul mencantumkan posisi pemula, namun deskripsi meminta {req_years}+ tahun pengalaman.",
                f"Title indicates an entry-level role, yet description asks for {req_years}+ years of experience.",
            )

    score = max(0, min(100, score))

    if score >= 80:
        category = "SAFE"
        label_id = "Aman / Terindikasi Asli"
        label_en = "Safe / Appears Legitimate"
    elif score >= 50:
        category = "GHOST_OR_CAUTION"
        label_id = "Waspada / Indikasi Ghost Job"
        label_en = "Caution / Possible Ghost Job"
    else:
        category = "HIGH_RISK_SCAM"
        label_id = "Risiko Tinggi / Indikasi Penipuan"
        label_en = "High Risk / Likely Scam"

    if not reasons:
        _add_reason(
            reasons, "NO_RED_FLAGS", 0,
            "Tidak Ditemukan Tanda Bahaya",
            "No Red Flags Detected",
            "Deskripsi, identitas perusahaan, dan kontak terlihat wajar.",
            "Description, company identity, and contact details appear normal.",
        )

    return {
        "score": score,
        "category": category,
        "label_id": label_id,
        "label_en": label_en,
        "reasons": reasons,
        "extracted": {
            "emails": extracted_emails,
            "primary_email": primary_email,
            "posting_age_days": posting_age_days,
            "word_count": word_count,
            "job_url": job_url,
        },
    }

