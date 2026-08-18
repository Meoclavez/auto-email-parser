"""Unit tests for JobManager and StateDatabase."""

import os
import shutil
import tempfile
import json
import unittest
from datetime import datetime, timezone

from src.config import StorageConfig
from src.storage.state_db import StateDatabase
from src.security.validator import AttachmentValidator
from src.file_handler.attachment_manager import AttachmentManager
from src.file_handler.markdown_writer import EmailMarkdownWriter
from src.storage.job_manager import JobManager
from src.email_receiver.models import EmailMessage, EmailAddress, AttachmentInfo, FilterResult


class TestJobManager(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_email_parser_")
        self.db_path = os.path.join(self.temp_dir, "test_jobs.db")
        self.jobs_dir = os.path.join(self.temp_dir, "jobs")
        self.quarantine_dir = os.path.join(self.temp_dir, "quarantine")

        self.storage_config = StorageConfig(
            base_dir=self.jobs_dir,
            quarantine_dir=self.quarantine_dir,
            database_path=self.db_path,
            job_id_prefix="JOB",
            file_permissions=0o640,
            dir_permissions=0o750
        )
        self.state_db = StateDatabase(self.db_path)
        self.validator = AttachmentValidator()
        self.att_manager = AttachmentManager(self.validator)
        self.md_writer = EmailMarkdownWriter()

        self.job_manager = JobManager(
            config=self.storage_config,
            state_db=self.state_db,
            attachment_manager=self.att_manager,
            markdown_writer=self.md_writer
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_job_id_generation_sequence(self):
        dt = datetime(2026, 8, 19, 12, 0, 0, tzinfo=timezone.utc)
        job_id_1 = self.state_db.get_next_job_id("JOB", dt)
        job_id_2 = self.state_db.get_next_job_id("JOB", dt)
        
        self.assertEqual(job_id_1, "JOB-20260819-0001")
        self.assertEqual(job_id_2, "JOB-20260819-0002")

    def test_create_job_end_to_end(self):
        pdf_data = b"%PDF-1.4\nTest PDF content"
        att = AttachmentInfo(
            original_filename="drawing_v1.pdf",
            sanitized_filename="",
            content_type="application/pdf",
            size_bytes=len(pdf_data),
            data=pdf_data
        )

        msg = EmailMessage(
            uid="55",
            message_id="<test-job-001@apex-engineering.com>",
            subject="RFQ-9002: Custom Brackets",
            sender=EmailAddress.parse("Apex Engineering <sales@apex-engineering.com>"),
            to_recipients=[EmailAddress.parse("intake@factory.com")],
            date_str="Wed, 19 Aug 2026 12:00:00 +0000",
            body_plain="Please quote on the attached drawing.",
            attachments=[att]
        )

        filter_res = FilterResult(is_match=True, matched_rules=["Subject keyword: RFQ"])

        res = self.job_manager.create_job(msg, filter_res)

        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["saved_attachments_count"], 1)
        self.assertEqual(res["quarantined_attachments_count"], 0)

        job_dir = res["job_dir"]
        self.assertTrue(os.path.exists(job_dir))
        self.assertTrue(os.path.exists(res["md_file"]))
        self.assertTrue(os.path.exists(res["manifest_file"]))

        # Verify folder name contains client slug and reference
        self.assertIn("apex-engineering", job_dir)
        self.assertIn("9002", job_dir)

        # Verify attachment was saved with consistent naming
        att_dir = os.path.join(job_dir, "attachments")
        saved_files = os.listdir(att_dir)
        self.assertEqual(len(saved_files), 1)
        self.assertTrue(saved_files[0].startswith("JOB-"))
        self.assertTrue(saved_files[0].endswith("drawing_v1.pdf"))

        # Verify manifest.json contents
        with open(res["manifest_file"], "r", encoding="utf-8") as f:
            manifest_data = json.load(f)
            self.assertEqual(manifest_data["job_id"], res["job_id"])
            self.assertEqual(manifest_data["client_id"], "apex-engineering")
            self.assertEqual(manifest_data["message_id"], "<test-job-001@apex-engineering.com>")
            self.assertEqual(len(manifest_data["attachments"]), 1)

        # Verify state database recorded processed status
        self.assertTrue(self.state_db.is_message_processed("<test-job-001@apex-engineering.com>"))


if __name__ == "__main__":
    unittest.main()
