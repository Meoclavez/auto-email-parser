"""Unit tests for web authentication, Argon2 hashing, sessions, and rate-limiting."""

import os
import shutil
import tempfile
import unittest
from src.storage.state_db import StateDatabase
from src.web.auth import PasswordManager, AuthService


class TestWebAuth(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_auth_")
        self.db_path = os.path.join(self.temp_dir, "auth_test.db")
        self.state_db = StateDatabase(self.db_path)
        self.auth_service = AuthService(self.state_db)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_password_hashing_and_verification(self):
        password = "SecurePassword123!"
        pw_hash = PasswordManager.hash_password(password)
        
        self.assertTrue(PasswordManager.verify_password(password, pw_hash))
        self.assertFalse(PasswordManager.verify_password("WrongPassword!", pw_hash))
        self.assertFalse(PasswordManager.verify_password("", pw_hash))

    def test_user_creation_and_auth_success(self):
        pw_hash = PasswordManager.hash_password("MySecretPass123!")
        user_id = self.state_db.create_user("john_doe", pw_hash, role="estimator")
        self.assertIsNotNone(user_id)

        success, session_id, user, msg = self.auth_service.authenticate_user(
            username="john_doe",
            password="MySecretPass123!",
            ip_address="192.168.1.50"
        )
        self.assertTrue(success)
        self.assertIsNotNone(session_id)
        self.assertEqual(user["username"], "john_doe")
        self.assertEqual(user["role"], "estimator")

        # Verify session lookup
        session_data = self.state_db.get_session(session_id)
        self.assertIsNotNone(session_data)
        self.assertEqual(session_data["username"], "john_doe")

    def test_auth_invalid_credentials(self):
        pw_hash = PasswordManager.hash_password("ValidPass123!")
        self.state_db.create_user("alice", pw_hash, role="admin")

        # Wrong password
        success, session_id, user, msg = self.auth_service.authenticate_user(
            username="alice",
            password="WrongPassword123!",
            ip_address="192.168.1.51"
        )
        self.assertFalse(success)
        self.assertIsNone(session_id)

        # Non-existent user
        success2, _, _, _ = self.auth_service.authenticate_user(
            username="non_existent",
            password="SomePassword",
            ip_address="192.168.1.51"
        )
        self.assertFalse(success2)

    def test_brute_force_ip_rate_limiting(self):
        ip = "10.0.0.99"
        pw_hash = PasswordManager.hash_password("ValidPass123!")
        self.state_db.create_user("target_user", pw_hash)

        # Fail 5 times
        for _ in range(5):
            success, _, _, _ = self.auth_service.authenticate_user("target_user", "wrong", ip)
            self.assertFalse(success)

        # 6th attempt should be blocked by rate limiter even with correct password
        success6, _, _, msg6 = self.auth_service.authenticate_user("target_user", "ValidPass123!", ip)
        self.assertFalse(success6)
        self.assertIn("Too many failed login attempts", msg6)


if __name__ == "__main__":
    unittest.main()
