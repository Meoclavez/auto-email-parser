"""Unit tests for credential encryption and master key management."""

import os
import shutil
import tempfile
import unittest
from src.security.encryption import CredentialCipher


class TestEncryption(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_enc_")
        self.key_path = os.path.join(self.temp_dir, "master.key")
        self.cipher = CredentialCipher(key_path=self.key_path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_encrypt_and_decrypt(self):
        secret_password = "SuperSecretPassword123!@#"
        ciphertext = self.cipher.encrypt(secret_password)
        
        self.assertNotEqual(ciphertext, secret_password)
        self.assertTrue(len(ciphertext) > 20)

        decrypted = self.cipher.decrypt(ciphertext)
        self.assertEqual(decrypted, secret_password)

    def test_empty_string(self):
        self.assertEqual(self.cipher.encrypt(""), "")
        self.assertEqual(self.cipher.decrypt(""), "")

    def test_tampered_ciphertext(self):
        ciphertext = self.cipher.encrypt("Password123")
        tampered = ciphertext[:-4] + "AAAA"
        decrypted = self.cipher.decrypt(tampered)
        self.assertEqual(decrypted, "")


if __name__ == "__main__":
    unittest.main()
