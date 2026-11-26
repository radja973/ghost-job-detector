import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from detector import detect_portal, normalize_job_url, parse_job_html, parse_posting_age_days


class TestJobScraper(unittest.TestCase):
    def test_detect_portal(self):
        self.assertEqual(detect_portal("https://www.linkedin.com/jobs/view/4474288524/"), "LinkedIn")
        self.assertEqual(detect_portal("https://glints.com/id/opportunities/jobs/123"), "Glints")
        self.assertEqual(detect_portal("https://id.indeed.com/viewjob?jk=abc"), "Indeed")
        self.assertEqual(detect_portal("https://www.upwork.com/jobs/~123"), "Upwork")
        self.assertEqual(detect_portal("https://dealls.com/loker/backend"), "Dealls")
        self.assertEqual(detect_portal("https://www.jobstreet.co.id/job/999"), "JobStreet")

    def test_normalize_linkedin_search_url(self):
        raw = "https://www.linkedin.com/jobs/search-results/?currentJobId=4474288524&refId=abc"
        self.assertEqual(normalize_job_url(raw), "https://www.linkedin.com/jobs/view/4474288524/")

    def test_parse_posting_age_days(self):
        self.assertEqual(parse_posting_age_days("1 month ago"), 30)
        self.assertEqual(parse_posting_age_days("2 weeks ago"), 14)
        self.assertEqual(parse_posting_age_days("5 hari yang lalu"), 5)
        self.assertEqual(parse_posting_age_days("Just now"), 0)

    def test_parse_linkedin_html(self):
        html = """
        <html>
          <head><title>Junior Java Developer at PT Pro Sigmaka Mandiri | LinkedIn Jobs</title></head>
          <body>
            <h1 class="top-card-layout__title">Junior Java Developer</h1>
            <a class="topcard__org-name-link">PT Pro Sigmaka Mandiri</a>
            <span class="posted-time-ago__text">1 month ago</span>
            <div class="show-more-less-html__markup">
              Developed and maintained backend applications using Java and Spring Boot.
            </div>
          </body>
        </html>
        """
        data = parse_job_html(html, "https://www.linkedin.com/jobs/view/4474288524/")
        self.assertEqual(data["portal"], "LinkedIn")
        self.assertEqual(data["title"], "Junior Java Developer")
        self.assertEqual(data["company"], "PT Pro Sigmaka Mandiri")
        self.assertEqual(data["posting_age_days"], 30)
        self.assertIn("Spring Boot", data["description"])

    def test_parse_json_ld_html(self):
        html = """
        <html>
          <head>
            <script type="application/ld+json">
              {
                "@context": "https://schema.org/",
                "@type": "JobPosting",
                "title": "Backend Engineer",
                "hiringOrganization": {"@type": "Organization", "name": "PT Contoh Teknologi"},
                "description": "<p>Build scalable APIs with Python and FastAPI. Contact hr@contohtek.co.id.</p>"
              }
            </script>
          </head>
          <body></body>
        </html>
        """
        data = parse_job_html(html, "https://glints.com/id/opportunities/jobs/123")
        self.assertEqual(data["portal"], "Glints")
        self.assertEqual(data["title"], "Backend Engineer")
        self.assertEqual(data["company"], "PT Contoh Teknologi")
        self.assertEqual(data["contact_email"], "hr@contohtek.co.id")


if __name__ == "__main__":
    unittest.main()
