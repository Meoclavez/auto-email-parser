"""Multi-mailbox manager with encrypted credential handling and connection diagnostics."""

import logging
import ssl
import socket
import imaplib
from typing import List, Dict, Any, Tuple, Optional
from src.config import IMAPConfig
from src.security.encryption import CredentialCipher
from src.storage.state_db import StateDatabase
from src.email_receiver.imap_client import IMAPReceiver
from src.email_receiver.models import EmailMessage

logger = logging.getLogger("EmailParser.MailboxManager")


class MailboxManager:
    """
    Coordinates multi-mailbox credentials, connection testing, and email fetching.
    """

    def __init__(self, state_db: StateDatabase, cipher: Optional[CredentialCipher] = None):
        self.state_db = state_db
        self.cipher = cipher or CredentialCipher()

    def test_mailbox_connection(
        self,
        server: str,
        port: int,
        use_ssl: bool,
        username: str,
        password: str,
        folder: str = "INBOX"
    ) -> Tuple[bool, str, int]:
        """
        Tests an IMAP connection and returns (success, message, unread_count).
        """
        client = None
        try:
            if use_ssl:
                ssl_context = ssl.create_default_context()
                client = imaplib.IMAP4_SSL(host=server, port=port, ssl_context=ssl_context, timeout=15)
            else:
                client = imaplib.IMAP4(host=server, port=port, timeout=15)
                if hasattr(client, 'starttls'):
                    try:
                        client.starttls()
                    except Exception:
                        pass

            typ, res = client.login(username, password)
            if typ != "OK":
                return False, f"Authentication failed: {res}", 0

            typ, res = client.select(folder)
            if typ != "OK":
                return False, f"Failed to select folder '{folder}': {res}", 0

            typ, data = client.search(None, "UNSEEN")
            unread_count = len(data[0].split()) if (typ == "OK" and data and data[0]) else 0

            return True, f"Successfully connected to '{folder}'. Found {unread_count} unread email(s).", unread_count

        except (socket.timeout, socket.error, ssl.SSLError, imaplib.IMAP4.error) as e:
            return False, f"Connection failed: {str(e)}", 0
        except Exception as e:
            return False, f"Unexpected error: {str(e)}", 0
        finally:
            if client:
                try:
                    client.close()
                except Exception:
                    pass
                try:
                    client.logout()
                except Exception:
                    pass

    def get_imap_config_for_mailbox(self, mb: Dict[str, Any]) -> IMAPConfig:
        """Converts database mailbox row into an active IMAPConfig with decrypted password."""
        decrypted_password = self.cipher.decrypt(mb.get("encrypted_password", ""))
        return IMAPConfig(
            server=mb["server"],
            port=int(mb["port"]),
            username=mb["username"],
            password=decrypted_password,
            use_ssl=bool(mb["use_ssl"]),
            mailbox=mb.get("folder", "INBOX"),
            poll_interval_seconds=int(mb.get("poll_interval_seconds", 60))
        )

    def fetch_emails_from_mailbox(self, mb: Dict[str, Any]) -> List[EmailMessage]:
        """Fetches unread emails from a single nominated mailbox."""
        config = self.get_imap_config_for_mailbox(mb)
        receiver = IMAPReceiver(config)
        
        try:
            if not receiver.connect():
                self.state_db.update_mailbox_status(mb["id"], "ERROR", "Failed to connect to IMAP server")
                return []

            emails = receiver.fetch_unread_emails()
            self.state_db.update_mailbox_status(mb["id"], "CONNECTED", None)
            return emails
        except Exception as e:
            logger.error(f"Error fetching from mailbox '{mb['name']}': {e}")
            self.state_db.update_mailbox_status(mb["id"], "ERROR", str(e))
            return []
        finally:
            receiver.close()
