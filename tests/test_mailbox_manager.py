"""Unit tests for mailbox management and multi-account storage."""

import os
import shutil
import tempfile
import unittest
from src.storage.state_db import StateDatabase
from src.security.encryption import CredentialCipher
from src.email_receiver.mailbox_manager import MailboxManager


class TestMailboxManager(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_mb_")
        self.db_path = os.path.join(self.temp_dir, "mb_test.db")
        self.key_path = os.path.join(self.temp_dir, "master.key")
        
        self.state_db = StateDatabase(self.db_path)
        self.cipher = CredentialCipher(key_path=self.key_path)
        self.manager = MailboxManager(self.state_db, self.cipher)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_add_and_retrieve_mailboxes(self):
        pw_encrypted = self.cipher.encrypt("SecretMailboxPass123!")
        mb_id = self.state_db.add_mailbox(
            name="Primary RFQ",
            server="imap.example.com",
            port=993,
            use_ssl=True,
            username="rfq@example.com",
            encrypted_password=pw_encrypted,
            folder="INBOX",
            poll_interval=60
        )
        self.assertIsNotNone(mb_id)

        all_mb = self.state_db.get_all_mailboxes()
        self.assertEqual(len(all_mb), 1)
        self.assertEqual(all_mb[0]["name"], "Primary RFQ")
        self.assertEqual(all_mb[0]["is_active"], 1)

        # Test IMAP config conversion with decrypted password
        mb_row = self.state_db.get_mailbox(mb_id)
        imap_conf = self.manager.get_imap_config_for_mailbox(mb_row)
        self.assertEqual(imap_conf.username, "rfq@example.com")
        self.assertEqual(imap_conf.password, "SecretMailboxPass123!")

    def test_toggle_and_delete_mailbox(self):
        pw_encrypted = self.cipher.encrypt("Pass123")
        mb_id = self.state_db.add_mailbox(
            name="Secondary",
            server="imap.example.com",
            port=993,
            use_ssl=True,
            username="sec@example.com",
            encrypted_password=pw_encrypted
        )

        # Toggle to Inactive
        self.state_db.toggle_mailbox(mb_id)
        active_list = self.state_db.get_active_mailboxes()
        self.assertEqual(len(active_list), 0)

        # Delete
        deleted = self.state_db.delete_mailbox(mb_id)
        self.assertTrue(deleted)
        self.assertEqual(len(self.state_db.get_all_mailboxes()), 0)


if __name__ == "__main__":
    unittest.main()
