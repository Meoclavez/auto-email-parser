"""Unit tests for attachment validator: magic bytes, extensions, zip bombs, and disguised binaries."""

import unittest
import zipfile
import io
from src.security.validator import AttachmentValidator


class TestValidator(unittest.TestCase):

    def setUp(self):
        self.validator = AttachmentValidator(
            max_file_size_mb=10,
            max_zip_uncompressed_mb=20,
            max_zip_entries=10
        )

    def test_valid_pdf_magic(self):
        pdf_bytes = b"%PDF-1.7\nSample PDF content for CAD enquiry"
        res = self.validator.validate("drawing.pdf", pdf_bytes)
        self.assertTrue(res.is_valid)
        self.assertFalse(res.is_quarantined)
        self.assertEqual(res.detected_type, "pdf")

    def test_valid_jpeg_magic(self):
        jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF"
        res = self.validator.validate("photo.jpg", jpeg_bytes)
        self.assertTrue(res.is_valid)
        self.assertEqual(res.detected_type, "jpeg")

    def test_valid_png_magic(self):
        png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        res = self.validator.validate("render.png", png_bytes)
        self.assertTrue(res.is_valid)
        self.assertEqual(res.detected_type, "png")

    def test_valid_dxf_cad(self):
        dxf_bytes = b"  0\nSECTION\n  2\nHEADER\n  0\nENDSEC\n  0\nEOF"
        res = self.validator.validate("part.dxf", dxf_bytes)
        self.assertTrue(res.is_valid)
        self.assertEqual(res.detected_type, "cad_dxf")

    def test_valid_step_cad(self):
        step_bytes = b"ISO-10303-21;\nHEADER;\nFILE_DESCRIPTION(('STEP AP214'),'1');\nENDSEC;\nEND-ISO-10303-21;"
        res = self.validator.validate("model.step", step_bytes)
        self.assertTrue(res.is_valid)
        self.assertEqual(res.detected_type, "cad_step")

    def test_blocked_executable_extension(self):
        exe_bytes = b"echo 'malicious script'"
        for ext in [".exe", ".bat", ".sh", ".vbs", ".ps1"]:
            res = self.validator.validate(f"malware{ext}", exe_bytes)
            self.assertFalse(res.is_valid)
            self.assertTrue(res.is_quarantined)
            self.assertIn("Forbidden", res.reason)

    def test_disguised_executable_mz_header(self):
        # Fake PDF that actually starts with Windows PE/MZ header
        fake_pdf = b"MZ\x90\x00\x03\x00\x00\x00This program cannot be run in DOS mode"
        res = self.validator.validate("invoice.pdf", fake_pdf)
        self.assertFalse(res.is_valid)
        self.assertTrue(res.is_quarantined)
        self.assertIn("Executable binary signature detected", res.reason)

    def test_disguised_executable_elf_header(self):
        # Fake JPG that starts with Linux ELF header
        fake_jpg = b"\x7fELF\x02\x01\x01\x00"
        res = self.validator.validate("image.jpg", fake_jpg)
        self.assertFalse(res.is_valid)
        self.assertTrue(res.is_quarantined)
        self.assertIn("Executable binary signature detected", res.reason)

    def test_file_size_exceeded(self):
        large_bytes = b"A" * (11 * 1024 * 1024)  # 11MB > 10MB limit
        res = self.validator.validate("large.pdf", large_bytes)
        self.assertFalse(res.is_valid)
        self.assertTrue(res.is_quarantined)
        self.assertIn("maximum allowed size", res.reason)

    def test_valid_zip_archive(self):
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            zf.writestr("model.step", b"ISO-10303-21; CAD DATA")
        
        res = self.validator.validate("project.zip", zip_buf.getvalue())
        self.assertTrue(res.is_valid)
        self.assertEqual(res.detected_type, "zip")

    def test_zip_with_path_traversal_entry(self):
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            zf.writestr("../../evil.txt", b"evil content")
        
        res = self.validator.validate("traversal.zip", zip_buf.getvalue())
        self.assertFalse(res.is_valid)
        self.assertTrue(res.is_quarantined)
        self.assertIn("path traversal", res.reason)

    def test_zip_with_executable_entry(self):
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            zf.writestr("payload.exe", b"malware content")
        
        res = self.validator.validate("dangerous.zip", zip_buf.getvalue())
        self.assertFalse(res.is_valid)
        self.assertTrue(res.is_quarantined)
        self.assertIn("forbidden executable", res.reason)


if __name__ == "__main__":
    unittest.main()
