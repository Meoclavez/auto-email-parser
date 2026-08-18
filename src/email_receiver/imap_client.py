"""Robust IMAP client for monitoring mailboxes, handling network drops with backoff, and parsing MIME messages."""

import imaplib
import email
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
import time
import socket
import ssl
import logging
from typing import List, Optional, Tuple, Generator
from datetime import datetime, timezone

from src.config import IMAPConfig
from src.email_receiver.models import EmailMessage, EmailAddress, AttachmentInfo

logger = logging.getLogger("EmailParser.IMAP")


class IMAPReceiver:
    """
    Manages resilient IMAP connection with automatic reconnection,
    exponential backoff, and RFC-compliant email parsing.
    """

    def __init__(self, config: IMAPConfig):
        self.config = config
        self._client: Optional[imaplib.IMAP4] = None
        self._is_connected = False

    def connect(self) -> bool:
        """Establishes an IMAP SSL connection with retry and exponential backoff."""
        retry_delay = 1
        max_attempts = 5

        for attempt in range(1, max_attempts + 1):
            try:
                logger.info(f"Connecting to IMAP server {self.config.server}:{self.config.port} (Attempt {attempt}/{max_attempts})...")
                
                if self.config.use_ssl:
                    ssl_context = ssl.create_default_context()
                    self._client = imaplib.IMAP4_SSL(
                        host=self.config.server,
                        port=self.config.port,
                        ssl_context=ssl_context,
                        timeout=self.config.connection_timeout
                    )
                else:
                    self._client = imaplib.IMAP4(
                        host=self.config.server,
                        port=self.config.port,
                        timeout=self.config.connection_timeout
                    )
                    if hasattr(self._client, 'starttls'):
                        try:
                            self._client.starttls()
                        except Exception as tls_err:
                            logger.warning(f"STARTTLS failed or not supported: {tls_err}")

                # Login
                typ, res = self._client.login(self.config.username, self.config.password)
                if typ != "OK":
                    raise imaplib.IMAP4.error(f"Login failed: {res}")

                # Select mailbox
                typ, res = self._client.select(self.config.mailbox)
                if typ != "OK":
                    raise imaplib.IMAP4.error(f"Failed to select mailbox '{self.config.mailbox}': {res}")

                self._is_connected = True
                logger.info(f"Successfully connected to mailbox '{self.config.mailbox}' as {self.config.username}")
                return True

            except (socket.timeout, socket.error, ssl.SSLError, imaplib.IMAP4.error, OSError) as e:
                logger.warning(f"Connection error (Attempt {attempt}/{max_attempts}): {e}. Retrying in {retry_delay}s...")
                self._disconnect_quietly()
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, self.config.max_retry_backoff)

        logger.error(f"Failed to connect to IMAP server after {max_attempts} attempts.")
        self._is_connected = False
        return False

    def fetch_unread_emails(self) -> List[EmailMessage]:
        """
        Searches and fetches unread (UNSEEN) emails from the mailbox.
        """
        if not self._is_connected or not self._client:
            if not self.connect():
                return []

        try:
            typ, data = self._client.search(None, "UNSEEN")
            if typ != "OK" or not data or not data[0]:
                return []

            email_uids = data[0].split()
            if not email_uids:
                return []

            logger.info(f"Found {len(email_uids)} unread email(s).")
            
            # Limit batch size to prevent memory spikes
            batch = email_uids[:self.config.max_emails_per_batch]
            parsed_emails: List[EmailMessage] = []

            for uid_bytes in batch:
                uid_str = uid_bytes.decode('ascii', errors='ignore')
                try:
                    typ, msg_data = self._client.fetch(uid_bytes, "(RFC822)")
                    if typ != "OK" or not msg_data:
                        continue

                    for response_part in msg_data:
                        if isinstance(response_part, tuple):
                            raw_email_bytes = response_part[1]
                            parsed_msg = self.parse_raw_email(raw_email_bytes, uid=uid_str)
                            parsed_emails.append(parsed_msg)

                except Exception as fetch_err:
                    logger.error(f"Error fetching email UID {uid_str}: {fetch_err}")

            return parsed_emails

        except (socket.error, imaplib.IMAP4.abort, imaplib.IMAP4.error) as e:
            logger.warning(f"IMAP session error while fetching: {e}. Resetting connection.")
            self._disconnect_quietly()
            return []

    def mark_as_read(self, uid_str: str) -> None:
        """Marks an email UID as read (\\Seen) on the server."""
        if not self._is_connected or not self._client:
            return
        try:
            self._client.store(uid_str.encode('ascii'), '+FLAGS', '\\Seen')
        except Exception as e:
            logger.warning(f"Failed to mark UID {uid_str} as \\Seen: {e}")

    def parse_raw_email(self, raw_bytes: bytes, uid: str = "") -> EmailMessage:
        """
        Parses raw RFC 822 email bytes into an EmailMessage data model.
        Handles multi-part decoding, character encodings, and attachment extraction.
        """
        msg = email.message_from_bytes(raw_bytes)

        # 1. Decode Headers
        subject = self._decode_header_str(msg.get("Subject", ""))
        sender_raw = self._decode_header_str(msg.get("From", ""))
        to_raw = self._decode_header_str(msg.get("To", ""))
        cc_raw = self._decode_header_str(msg.get("Cc", ""))
        message_id = msg.get("Message-ID", "").strip()
        date_raw = msg.get("Date", "")

        sender = EmailAddress.parse(sender_raw)
        to_recipients = [EmailAddress.parse(addr) for addr in to_raw.split(",") if addr.strip()]
        cc_recipients = [EmailAddress.parse(addr) for addr in cc_raw.split(",") if addr.strip()]

        date_dt = None
        if date_raw:
            try:
                date_dt = parsedate_to_datetime(date_raw)
            except Exception:
                date_dt = datetime.now(timezone.utc)

        # 2. Extract Body and Attachments
        body_plain_parts: List[str] = []
        body_html_parts: List[str] = []
        attachments: List[AttachmentInfo] = []

        if msg.is_multipart():
            for part in msg.walk():
                content_disposition = str(part.get("Content-Disposition", ""))
                content_type = part.get_content_type().lower()
                filename = part.get_filename()

                # Check if this part is an attachment
                is_attachment = ("attachment" in content_disposition.lower()) or (filename is not None)

                if is_attachment:
                    decoded_filename = self._decode_header_str(filename or "unnamed_attachment")
                    payload = part.get_payload(decode=True)
                    if payload:
                        att_info = AttachmentInfo(
                            original_filename=decoded_filename,
                            sanitized_filename="",
                            content_type=content_type or "application/octet-stream",
                            size_bytes=len(payload),
                            data=payload
                        )
                        attachments.append(att_info)
                elif content_type == "text/plain" and "attachment" not in content_disposition.lower():
                    decoded_text = self._decode_payload(part)
                    if decoded_text:
                        body_plain_parts.append(decoded_text)
                elif content_type == "text/html" and "attachment" not in content_disposition.lower():
                    decoded_html = self._decode_payload(part)
                    if decoded_html:
                        body_html_parts.append(decoded_html)
        else:
            content_type = msg.get_content_type().lower()
            decoded_text = self._decode_payload(msg)
            if content_type == "text/html":
                body_html_parts.append(decoded_text)
            else:
                body_plain_parts.append(decoded_text)

        body_plain = "\n\n".join(body_plain_parts).strip()
        body_html = "\n\n".join(body_html_parts).strip()

        # Fallback message_id if absent
        if not message_id:
            import hashlib
            hash_input = f"{sender_raw}{date_raw}{subject}".encode('utf-8', errors='ignore')
            message_id = f"<synth-{hashlib.sha256(hash_input).hexdigest()[:16]}@local>"

        return EmailMessage(
            uid=uid,
            message_id=message_id,
            subject=subject,
            sender=sender,
            to_recipients=to_recipients,
            cc_recipients=cc_recipients,
            date_str=date_raw,
            date_dt=date_dt,
            body_plain=body_plain,
            body_html=body_html,
            attachments=attachments,
            raw_headers=dict(msg.items())
        )

    def _decode_header_str(self, header_val: str) -> str:
        """Decodes RFC 2047 encoded email headers."""
        if not header_val:
            return ""
        try:
            decoded_chunks = decode_header(header_val)
            header_parts = []
            for text, charset in decoded_chunks:
                if isinstance(text, bytes):
                    encoding = charset or 'utf-8'
                    try:
                        header_parts.append(text.decode(encoding, errors='replace'))
                    except (LookupError, UnicodeDecodeError):
                        header_parts.append(text.decode('latin-1', errors='replace'))
                else:
                    header_parts.append(str(text))
            return " ".join(header_parts).strip()
        except Exception:
            return str(header_val).strip()

    def _decode_payload(self, part) -> str:
        """Extracts and decodes email payload with multi-codec fallback."""
        payload = part.get_payload(decode=True)
        if not payload:
            return ""

        charset = part.get_content_charset() or 'utf-8'
        for enc in (charset, 'utf-8', 'latin-1', 'windows-1252', 'cp1252', 'iso-8859-1'):
            try:
                return payload.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue

        return payload.decode('utf-8', errors='replace')

    def _disconnect_quietly(self):
        """Cleanly disconnects the IMAP client if open."""
        self._is_connected = False
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            try:
                self._client.logout()
            except Exception:
                pass
            self._client = None

    def close(self):
        """Public close method."""
        self._disconnect_quietly()
