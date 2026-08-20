"""Credential encryption at rest using Fernet (AES-128-CBC with HMAC authentication)."""

import os
import base64
import logging
from typing import Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger("EmailParser.Encryption")


class CredentialCipher:
    """
    Encrypts and decrypts sensitive mailbox passwords and secrets at rest.
    Guarantees authenticated symmetric encryption.
    """

    def __init__(self, key_path: str = "config/master.key", secret_env_var: str = "APP_MASTER_KEY"):
        self.key_path = key_path
        self.secret_env_var = secret_env_var
        self._fernet: Fernet = self._initialize_fernet()

    def _initialize_fernet(self) -> Fernet:
        """Loads master key from environment or local protected keyfile."""
        env_key = os.getenv(self.secret_env_var)
        if env_key:
            key_bytes = env_key.encode('utf-8') if isinstance(env_key, str) else env_key
            try:
                return Fernet(key_bytes)
            except Exception:
                # Derive 32-byte urlsafe base64 key using PBKDF2 if custom passphrase was supplied
                kdf = PBKDF2HMAC(
                    algorithm=hashes.SHA256(),
                    length=32,
                    salt=b"auto-email-parser-salt",
                    iterations=100000,
                )
                derived = base64.urlsafe_b64encode(kdf.derive(key_bytes))
                return Fernet(derived)

        # Fallback to local master.key file
        os.makedirs(os.path.dirname(os.path.abspath(self.key_path)), exist_ok=True)
        if not os.path.exists(self.key_path):
            new_key = Fernet.generate_key()
            temp_path = f"{self.key_path}.tmp"
            with open(temp_path, "wb") as f:
                f.write(new_key)
            os.chmod(temp_path, 0o600)
            os.replace(temp_path, self.key_path)
            logger.info(f"Generated new master encryption key at {self.key_path}")

        with open(self.key_path, "rb") as f:
            key_data = f.read().strip()
            return Fernet(key_data)

    def encrypt(self, plaintext: str) -> str:
        """Encrypts plaintext string and returns urlsafe base64 encoded ciphertext string."""
        if not plaintext:
            return ""
        encrypted_bytes = self._fernet.encrypt(plaintext.encode('utf-8'))
        return encrypted_bytes.decode('utf-8')

    def decrypt(self, ciphertext: str) -> str:
        """Decrypts ciphertext string back into plaintext."""
        if not ciphertext:
            return ""
        try:
            decrypted_bytes = self._fernet.decrypt(ciphertext.encode('utf-8'))
            return decrypted_bytes.decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to decrypt credential payload: {e}")
            return ""
