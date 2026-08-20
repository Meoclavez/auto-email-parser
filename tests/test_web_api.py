"""Integration tests for web dashboard API routes and security headers."""

import os
import shutil
import tempfile
import json
import unittest
from flask import Flask

from src.config import AppConfig, IMAPConfig, FilterConfig, StorageConfig, SecurityConfig
from src.service import EmailParserService
from src.web.app import create_app
from src.web.auth import PasswordManager


class TestWebAPI(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_web_api_")
        self.jobs_dir = os.path.join(self.temp_dir, "jobs")
        self.quarantine_dir = os.path.join(self.temp_dir, "quarantine")
        self.db_path = os.path.join(self.temp_dir, "web_test.db")

        os.makedirs(self.jobs_dir, exist_ok=True)
        os.makedirs(self.quarantine_dir, exist_ok=True)

        self.config = AppConfig(
            imap=IMAPConfig(server="localhost", username="test@local", password="pw"),
            filters=FilterConfig(required_subject_keywords=["RFQ"]),
            storage=StorageConfig(
                base_dir=self.jobs_dir,
                quarantine_dir=self.quarantine_dir,
                database_path=self.db_path
            ),
            security=SecurityConfig()
        )

        self.service = EmailParserService(self.config)
        self.app = create_app(self.config, self.service)
        self.client = self.app.test_client()

        # Create Admin User and Session
        self.admin_password = "AdminSecret123!"
        pw_hash = PasswordManager.hash_password(self.admin_password)
        self.admin_id = self.app.config["STATE_DB"].create_user("admin_user", pw_hash, role="admin")
        self.admin_session = self.app.config["STATE_DB"].create_session(self.admin_id, "admin_user", "admin")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_security_headers_present(self):
        res = self.client.get("/login")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(res.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertIn("default-src 'self'", res.headers.get("Content-Security-Policy", ""))

    def test_unauthenticated_api_returns_401(self):
        res = self.client.get("/api/jobs")
        self.assertEqual(res.status_code, 401)
        data = res.get_json()
        self.assertEqual(data.get("error"), "Unauthorized")

    def test_login_api_and_cookie_issuance(self):
        res = self.client.post("/api/auth/login", json={
            "username": "admin_user",
            "password": self.admin_password
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        # Check cookie header
        set_cookie = res.headers.get("Set-Cookie", "")
        self.assertIn("session_id=", set_cookie)
        self.assertIn("HttpOnly", set_cookie)

    def test_get_stats_authenticated(self):
        self.client.set_cookie("session_id", self.admin_session)
        res = self.client.get("/api/stats")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("TOTAL", data)
        self.assertIn("QUARANTINED", data)
        self.assertIn("DISK_FREE_MB", data)

    def test_job_listing_and_detail(self):
        # Insert mock job in state database
        state_db = self.app.config["STATE_DB"]
        state_db.record_start("<msg-99@acme.com>", "99", "sales@acme.com", "RFQ-101: Brackets")
        
        job_dir = os.path.join(self.jobs_dir, "JOB-20260819-0001_acme")
        att_dir = os.path.join(job_dir, "attachments")
        os.makedirs(att_dir, exist_ok=True)
        
        md_file = os.path.join(job_dir, "email_content.md")
        with open(md_file, "w", encoding="utf-8") as f:
            f.write("# Email Content for RFQ-101\n\nPlease quote on drawing.")

        manifest_file = os.path.join(job_dir, "manifest.json")
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump({"job_id": "JOB-20260819-0001", "attachments": [{"filename": "drawing.pdf", "size_bytes": 1024}]}, f)

        # Create sample drawing attachment
        sample_pdf = os.path.join(att_dir, "JOB-20260819-0001_01_drawing.pdf")
        with open(sample_pdf, "wb") as f:
            f.write(b"%PDF-1.4\nTest Drawing")

        state_db.record_success("<msg-99@acme.com>", "JOB-20260819-0001", manifest_file, uid="99", sender="sales@acme.com", subject="RFQ-101: Brackets")

        self.client.set_cookie("session_id", self.admin_session)
        
        # 1. Test listing
        res_list = self.client.get("/api/jobs")
        self.assertEqual(res_list.status_code, 200)
        jobs_data = res_list.get_json()
        self.assertEqual(len(jobs_data["jobs"]), 1)
        self.assertEqual(jobs_data["jobs"][0]["job_id"], "JOB-20260819-0001")

        # 2. Test job detail
        res_detail = self.client.get("/api/jobs/JOB-20260819-0001")
        self.assertEqual(res_detail.status_code, 200)
        detail_data = res_detail.get_json()
        self.assertEqual(detail_data["job"]["job_id"], "JOB-20260819-0001")
        self.assertIsNotNone(detail_data["manifest"])

        # 3. Test markdown retrieval
        res_md = self.client.get("/api/jobs/JOB-20260819-0001/markdown")
        self.assertEqual(res_md.status_code, 200)
        self.assertIn("Email Content for RFQ-101", res_md.get_json()["content"])

        # 4. Test safe attachment download
        res_dl = self.client.get("/api/jobs/JOB-20260819-0001/attachments/JOB-20260819-0001_01_drawing.pdf")
        self.assertEqual(res_dl.status_code, 200)
        self.assertEqual(res_dl.data, b"%PDF-1.4\nTest Drawing")
        self.assertEqual(res_dl.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertIn("attachment", res_dl.headers.get("Content-Disposition", ""))

        # 5. Test path traversal defense on download
        res_traversal = self.client.get("/api/jobs/JOB-20260819-0001/attachments/../../../../etc/passwd")
        self.assertIn(res_traversal.status_code, [403, 404])


if __name__ == "__main__":
    unittest.main()
