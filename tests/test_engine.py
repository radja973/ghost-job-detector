import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from detector import analyze_job_posting


class TestGhostJobDetector(unittest.TestCase):
    def test_legitimate_job_scores_safe(self):
        res = analyze_job_posting(
            title="Backend Java Developer",
            company="PT Nusantara Digital Tbk",
            contact_email="recruitment@nusantaradigital.co.id",
            posting_age_days=5,
            description=(
                "We are looking for a Backend Java Developer to join our Core Payments engineering team. "
                "Responsibilities include designing REST APIs with Spring Boot, writing automated tests, "
                "collaborating with product managers, and maintaining PostgreSQL databases. "
                "Requirements: 1-2 years experience in Java, Spring Boot, Git, and SQL."
            ),
        )
        self.assertEqual(res["category"], "SAFE")
        self.assertGreaterEqual(res["score"], 80)

    def test_scam_job_scores_high_risk(self):
        res = analyze_job_posting(
            title="Admin Operasional",
            company="PT Maju Bersama Tbk",
            contact_email="hrd.recruitment99@gmail.com",
            posting_age_days=2,
            description=(
                "Gaji hingga Rp 50 juta per bulan tanpa pengalaman. Interview hanya via Telegram "
                "t.me/hrd_indo. Peserta wajib transfer biaya administrasi dan seragam ke rekening pribadi."
            ),
        )
        self.assertEqual(res["category"], "HIGH_RISK_SCAM")
        self.assertLess(res["score"], 50)
        codes = {r["code"] for r in res["reasons"]}
        self.assertIn("UPFRONT_FEE", codes)
        self.assertIn("UNOFFICIAL_CHANNEL", codes)
        self.assertIn("FREE_EMAIL_CORPORATE", codes)

    def test_ghost_job_scores_caution(self):
        res = analyze_job_posting(
            title="Fresh Graduate Software Engineer",
            company="Confidential",
            posting_age_days=62,
            description="Looking for fresh graduate with 6+ years of experience in enterprise systems.",
        )
        self.assertEqual(res["category"], "GHOST_OR_CAUTION")
        self.assertGreaterEqual(res["score"], 50)
        self.assertLess(res["score"], 80)
        codes = {r["code"] for r in res["reasons"]}
        self.assertIn("STALE_POSTING_45D", codes)
        self.assertIn("MISSING_COMPANY", codes)
        self.assertIn("VAGUE_DESCRIPTION", codes)
        self.assertIn("CONTRADICTORY_REQUIREMENT", codes)


if __name__ == "__main__":
    unittest.main()
