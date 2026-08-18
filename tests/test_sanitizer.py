"""Unit tests for filename sanitization and security path traversal defense."""

import unittest
from src.security.sanitizer import (
    sanitize_filename,
    sanitize_identifier,
    extract_client_identifier,
    extract_job_reference
)
from src.email_receiver.models import EmailAddress


class TestSanitizer(unittest.TestCase):

    def test_path_traversal_posix(self):
        malicious = "../../../etc/passwd"
        cleaned = sanitize_filename(malicious)
        self.assertEqual(cleaned, "passwd")
        self.assertNotIn("/", cleaned)
        self.assertNotIn("..", cleaned)

    def test_path_traversal_windows(self):
        malicious = "..\\..\\Windows\\System32\\cmd.exe"
        cleaned = sanitize_filename(malicious)
        self.assertEqual(cleaned, "cmd.exe")
        self.assertNotIn("\\", cleaned)

    def test_null_byte_injection(self):
        malicious = "legit_file.pdf\0.exe"
        cleaned = sanitize_filename(malicious)
        self.assertNotIn("\0", cleaned)
        self.assertTrue(cleaned.endswith(".pdf.exe") or cleaned.endswith(".exe") or "legit_file" in cleaned)

    def test_reserved_device_names(self):
        self.assertEqual(sanitize_filename("CON.pdf"), "CON_file.pdf")
        self.assertEqual(sanitize_filename("NUL.txt"), "NUL_file.txt")
        self.assertEqual(sanitize_filename("aux.dxf"), "aux_file.dxf")

    def test_special_characters_removal(self):
        raw = "part:01*revision?#2<final>.dxf"
        cleaned = sanitize_filename(raw)
        self.assertEqual(cleaned, "part_01_revision_#2_final.dxf")

    def test_empty_or_whitespace_filename(self):
        self.assertEqual(sanitize_filename(""), "attachment.dat")
        self.assertEqual(sanitize_filename("   "), "attachment.dat")
        self.assertEqual(sanitize_filename("   .pdf"), "attachment.pdf")

    def test_max_length_truncation(self):
        long_name = "a" * 200 + ".step"
        cleaned = sanitize_filename(long_name, max_length=50)
        self.assertTrue(len(cleaned) <= 50)
        self.assertTrue(cleaned.endswith(".step"))

    def test_sanitize_identifier(self):
        self.assertEqual(sanitize_identifier("Acme Corp & Sons!"), "acme-corp-sons")
        self.assertEqual(sanitize_identifier("  Precision CAD  "), "precision-cad")
        self.assertEqual(sanitize_identifier(""), "client")

    def test_extract_client_identifier(self):
        addr1 = EmailAddress(raw="John Doe <john@precision-eng.co.uk>", name="John Doe", email="john@precision-eng.co.uk", domain="precision-eng.co.uk")
        self.assertEqual(extract_client_identifier(addr1), "precision-eng")

        # Public provider fallback to name
        addr2 = EmailAddress(raw="Alice Smith <alice@gmail.com>", name="Alice Smith", email="alice@gmail.com", domain="gmail.com")
        self.assertEqual(extract_client_identifier(addr2), "alice-smith")

    def test_extract_job_reference(self):
        self.assertEqual(extract_job_reference("Urgent: Quote RFQ-88219 for CNC parts"), "88219")
        self.assertEqual(extract_job_reference("Re: Project Order #JOB994"), "job994")
        self.assertIsNone(extract_job_reference("General enquiry regarding your services"))


if __name__ == "__main__":
    unittest.main()
