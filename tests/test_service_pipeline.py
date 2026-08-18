"""Integration tests for the complete email processing pipeline."""

import os
import shutil
import tempfile
import unittest
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.mime.image import MIMEImage

from src.config import AppConfig, IMAPConfig, FilterConfig, StorageConfig, SecurityConfig
from src.service import EmailParserService
from src.email_receiver.imap_client import IMAPReceiver


class TestServicePipeline(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_pipeline_")
        self.jobs_dir = os.path.join(self.temp_dir, "jobs")
        self.quarantine_dir = os.path.join(self.temp_dir, "quarantine")
        self.db_path = os.path.join(self.temp_dir, "jobs.db")

        self.config = AppConfig(
            imap=IMAPConfig(
                server="localhost",
                port=993,
                username="test@local",
                password="password",
                mark_as_read=False
            ),
            filters=FilterConfig(
                required_subject_keywords=["RFQ", "Quote", "Enquiry"],
                excluded_subject_keywords=["Out of Office"],
                allowed_sender_domains=[],
                blocked_sender_domains=["spammer.com"],
            ),
            storage=StorageConfig(
                base_dir=self.jobs_dir,
                quarantine_dir=self.quarantine_dir,
                database_path=self.db_path,
                min_free_disk_mb=10
            ),
            security=SecurityConfig(
                max_file_size_mb=10,
                allow_zip_archives=True
            ),
            log_level="ERROR"
        )

        self.service = EmailParserService(self.config)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_raw_email(
        self,
        subject: str,
        sender: str,
        to: str,
        message_id: str,
        body_text: str,
        attachments: list
    ) -> bytes:
        """Helper to construct raw RFC 822 MIME email bytes."""
        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = to
        msg["Message-ID"] = message_id
        msg["Date"] = "Wed, 19 Aug 2026 14:30:00 +0000"

        msg.attach(MIMEText(body_text, "plain", "utf-8"))

        for filename, data, maintype, subtype in attachments:
            part = MIMEApplication(data, _subtype=subtype)
            part.add_header("Content-Disposition", "attachment", filename=filename)
            msg.attach(part)

        return msg.as_bytes()

    def test_pipeline_valid_enquiry_with_mixed_attachments(self):
        # Attachments: 1 valid PDF, 1 valid DXF, 1 malicious EXE disguised as PDF
        pdf_data = b"%PDF-1.4\nDetailed CAD Drawing specification..."
        dxf_data = b"0\nSECTION\n2\nHEADER\n0\nENDSEC\n0\nEOF"
        malicious_data = b"MZ\x90\x00Executable binary payload..."

        raw_email = self._create_raw_email(
            subject="RFQ-1042: Precision Machined Flanges",
            sender="Delta Aerospace <purchasing@delta-aero.com>",
            to="enquiries@company.com",
            message_id="<delta-rfq-1042@delta-aero.com>",
            body_text="Hi,\n\nPlease quote for 250 units according to the attached drawings.\n\nThanks,\nJohn",
            attachments=[
                ("flange_drawing.pdf", pdf_data, "application", "pdf"),
                ("flange_model.dxf", dxf_data, "application", "dxf"),
                ("trojan.pdf", malicious_data, "application", "pdf")  # Disguised EXE
            ]
        )

        parsed_email = self.service.imap_client.parse_raw_email(raw_email, uid="1001")
        self.assertEqual(len(parsed_email.attachments), 3)

        job_result = self.service.process_single_email(parsed_email)

        self.assertIsNotNone(job_result)
        self.assertEqual(job_result["status"], "SUCCESS")
        self.assertEqual(job_result["saved_attachments_count"], 2)
        self.assertEqual(job_result["quarantined_attachments_count"], 1)

        # Check job directory
        job_dir = job_result["job_dir"]
        self.assertTrue(os.path.exists(job_dir))
        self.assertTrue(os.path.exists(job_result["md_file"]))
        self.assertTrue(os.path.exists(job_result["manifest_file"]))

        # Check saved attachments
        att_dir = os.path.join(job_dir, "attachments")
        saved_files = sorted(os.listdir(att_dir))
        self.assertEqual(len(saved_files), 2)
        self.assertTrue("flange_drawing.pdf" in saved_files[0])
        self.assertTrue("flange_model.dxf" in saved_files[1])

        # Check quarantine directory contains the blocked disguised binary
        quar_files = os.listdir(self.quarantine_dir)
        self.assertEqual(len(quar_files), 1)
        self.assertTrue(quar_files[0].endswith(".quarantine"))

        # Verify email_content.md contents
        with open(job_result["md_file"], "r", encoding="utf-8") as f:
            md_content = f.read()
            self.assertIn("# Email Enquiry: RFQ-1042: Precision Machined Flanges", md_content)
            self.assertIn("Delta Aerospace", md_content)
            self.assertIn("flange_drawing.pdf", md_content)
            self.assertIn("flange_model.dxf", md_content)
            self.assertIn("> [!WARNING]", md_content)
            self.assertIn("Executable binary signature detected", md_content)

        # Test Idempotency: Processing the same message again should be skipped
        duplicate_res = self.service.process_single_email(parsed_email)
        self.assertIsNone(duplicate_res)

        # Verify stats in DB
        stats = self.service.state_db.get_stats()
        self.assertEqual(stats.get("PROCESSED", 0), 1)
        self.assertEqual(stats.get("TOTAL", 0), 1)

    def test_pipeline_filters_out_spam_and_unrelated(self):
        spam_email = self._create_raw_email(
            subject="Cheap loans and credit cards",
            sender="Spam <marketing@spammer.com>",
            to="enquiries@company.com",
            message_id="<spam-999@spammer.com>",
            body_text="Click here to claim your prize.",
            attachments=[]
        )
        parsed_spam = self.service.imap_client.parse_raw_email(spam_email, uid="1002")
        res = self.service.process_single_email(parsed_spam)
        self.assertIsNone(res)

        stats = self.service.state_db.get_stats()
        self.assertEqual(stats.get("IGNORED", 0), 1)


if __name__ == "__main__":
    unittest.main()
