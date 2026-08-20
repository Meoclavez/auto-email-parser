"""Unit tests for estimator job notes, status transitions, and user registration."""

import os
import shutil
import tempfile
import unittest
from src.storage.state_db import StateDatabase
from src.web.auth import PasswordManager


class TestJobNotesAndUsers(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_notes_")
        self.db_path = os.path.join(self.temp_dir, "notes_test.db")
        self.state_db = StateDatabase(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_company_and_user_creation(self):
        comp_id = self.state_db.create_company("Acme Precision", "acme-precision.co.uk")
        self.assertIsNotNone(comp_id)

        pw_hash = PasswordManager.hash_password("UserPass123!")
        user_id = self.state_db.create_user(
            username="jane_estimator",
            password_hash=pw_hash,
            role="estimator",
            full_name="Jane Smith",
            email="jane@acme-precision.co.uk",
            company_id=comp_id
        )
        self.assertIsNotNone(user_id)

        user = self.state_db.get_user_by_username("jane_estimator")
        self.assertEqual(user["full_name"], "Jane Smith")
        self.assertEqual(user["role"], "estimator")

    def test_job_notes_and_status_transitions(self):
        self.state_db.record_start("<job-999@domain.com>", "999", "client@domain.com", "RFQ-Titanium")
        self.state_db.record_success("<job-999@domain.com>", "JOB-20260820-0001", "manifest.json", "999", "client@domain.com", "RFQ-Titanium")

        # 1. Add notes
        self.state_db.add_job_note("JOB-20260820-0001", 1, "estimator_1", "Material requires Ti-6Al-4V bead blasting")
        notes = self.state_db.get_job_notes("JOB-20260820-0001")
        self.assertEqual(len(notes), 1)
        self.assertIn("Ti-6Al-4V", notes[0]["note_text"])

        # 2. Status transition
        self.state_db.update_job_status("JOB-20260820-0001", "IN_REVIEW")
        job = self.state_db.get_job_by_id("JOB-20260820-0001")
        self.assertEqual(job["status"], "IN_REVIEW")

        self.state_db.update_job_status("JOB-20260820-0001", "QUOTED")
        job_quoted = self.state_db.get_job_by_id("JOB-20260820-0001")
        self.assertEqual(job_quoted["status"], "QUOTED")


if __name__ == "__main__":
    unittest.main()
