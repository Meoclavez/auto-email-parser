"""IMAP Email Client with SSL/TLS, auto-reconnect, exponential backoff, and robust MIME parsing."""

import email
import email.header
import email.utils
import imaplib
import logging
import socket
import ssl
import time
from typing import List, Optional, Tuple, Dict, Any

from src.config import IMAPConfig
from src.email_receiver.models import EmailMessage, EmailAddress, AttachmentInfo
from src.security.sanitizer import sanitize_filename

logger = logging.getLogger("EmailParser.IMAP")


class IMAPReceiver:
    """
    Handles robust connection, authentication, retrieval, and parsing of emails from an IMAP server.
    Utilizes permanent IMAP UIDs to guarantee state idempotency.
    """

    def __init__(self, config: IMAPConfig):
        self.config = config
        self._client: Optional[imaplib.IMAP4] = None
        self._is_connected = False

    def connect(self) -> bool:
        """Establishes SSL/TLS connection and authenticates with retry/backoff."""
        max_retries = 3
        delay = 2.0

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"Connecting to IMAP {self.config.server}:{self.config.port} (Attempt {attempt}/{max_retries})...")
                
                if self.config.use_ssl:
                    ssl_context = ssl.create_default_context()
                    self._client = imaplib.IMAP4_SSL(
                        host=self.config.server,
                        port=self.config.port,
                        ssl_context=ssl_context,
                        timeout=self.config.timeout_seconds
                    )
                else:
                    self._client = imaplib.IMAP4(
                        host=self.config.server,
                        port=self.config.port,
                        timeout=self.config.timeout_seconds
                    )
                    if hasattr(self._client, 'starttls'):
                        try:
                            self._client.starttls()
                        except Exception as e:
                            logger.warning(f"STARTTLS failed or not supported: {e}")

                typ, res = self._client.login(self.config.username, self.config.password)
                if typ != "OK":
                    raise imaplib.IMAP4.error(f"Login failed: {res}")

                typ, res = self._client.select(self.config.mailbox)
                if typ != "OK":
                    raise imaplib.IMAP4.error(f"Failed to select folder '{self.config.mailbox}': {res}")

                self._is_connected = True
                logger.info(f"Connected and authenticated to '{self.config.mailbox}' on {self.config.server}.")
                return True

            except (socket.timeout, socket.error, ssl.SSLError, imaplib.IMAP4.error) as e:
                logger.warning(f"Connection attempt {attempt} failed: {e}")
                self._is_connected = False
                if attempt < max_retries:
                    time.sleep(delay)
                    delay *= 2.0

        logger.error(f"Failed to connect to IMAP server after {max_retries} attempts.")
        return False

    def fetch_unread_emails(self) -> List[EmailMessage]:
        """Fetches all UNSEEN emails using permanent IMAP UIDs."""
        if not self._is_connected or not self._client:
            if not self.connect():
                return []

        messages: List[EmailMessage] = []
        try:
            typ, data = self._client.uid("search", None, "UNSEEN")
            if typ != "OK" or not data or not data[0]:
                logger.debug("No unread emails found in mailbox.")
                return []

            uid_list = data[0].split()
            logger.info(f"Found {len(uid_list)} unread email(s).")

            for uid_bytes in uid_list:
                uid_str = uid_bytes.decode('ascii')
                try:
                    typ, msg_data = self._client.uid("fetch", uid_bytes, "(RFC822)")
                    if typ != "OK" or not msg_data or not msg_data[0]:
                        logger.warning(f"Failed to fetch UID {uid_str}")
                        continue

                    raw_email_bytes = msg_data[0][1]
                    email_obj = self.parse_raw_email(raw_email_bytes, uid=uid_str)
                    messages.append(email_obj)
                except Exception as e:
                    logger.error(f"Error parsing email UID {uid_str}: {e}", exc_info=True)

        except (socket.error, imaplib.IMAP4.error) as e:
            logger.error(f"IMAP error while fetching emails: {e}")
            self._is_connected = False

        return messages

    def parse_raw_email(self, raw_bytes: bytes, uid: str = "") -> EmailMessage:
        """Parses raw RFC822 bytes into a structured EmailMessage with RFC 5322 compliance."""
        msg = email.message_from_bytes(raw_bytes)

        message_id = self._clean_header(msg.get("Message-ID", "")).strip("<>") or f"gen-{time.time()}-{uid}"
        subject = self._decode_header_str(msg.get("Subject", ""))
        date_str = msg.get("Date", "")

        from_raw = msg.get("From", "")
        sender = self._parse_single_address(from_raw)

        to_raw = msg.get("To", "")
        to_recipients = self._parse_address_list(to_raw)

        cc_raw = msg.get("Cc", "")
        cc_recipients = self._parse_address_list(cc_raw)

        body_plain = ""
        body_html = ""
        attachments: List[AttachmentInfo] = []

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", "")).lower()
                filename = part.get_filename()

                if filename:
                    filename = self._decode_header_str(filename)

                is_attachment = ("attachment" in content_disposition) or (filename is not None and "inline" not in content_disposition)

                if is_attachment and filename:
                    payload = part.get_payload(decode=True)
                    if payload:
                        attachments.append(AttachmentInfo(
                            original_filename=filename,
                            sanitized_filename=sanitize_filename(filename),
                            content_type=content_type,
                            size_bytes=len(payload),
                            data=payload
                        ))
                elif content_type == "text/plain" and not is_attachment:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        body_plain += self._decode_payload(payload, charset)
                elif content_type == "text/html" and not is_attachment:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        body_html += self._decode_payload(payload, charset)
        else:
            content_type = msg.get_content_type()
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                decoded_text = self._decode_payload(payload, charset)
                if content_type == "text/html":
                    body_html = decoded_text
                else:
                    body_plain = decoded_text

        raw_headers: Dict[str, str] = {k: self._decode_header_str(v) for k, v in msg.items()}

        return EmailMessage(
            uid=uid,
            message_id=message_id,
            subject=subject,
            sender=sender,
            to_recipients=to_recipients,
            cc_recipients=cc_recipients,
            date_str=date_str,
            body_plain=body_plain,
            body_html=body_html,
            attachments=attachments,
            raw_headers=raw_headers
        )

    def mark_as_read(self, uid: str) -> bool:
        """Marks an email as read using its permanent IMAP UID."""
        if not self._is_connected or not self._client or not uid:
            return False
        try:
            self._client.uid("store", uid.encode('ascii'), "+FLAGS", "(\\Seen)")
            return True
        except Exception as e:
            logger.error(f"Failed to mark email UID {uid} as read: {e}")
            return False

    def close(self):
        """Cleanly logs out and closes IMAP connection."""
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
        self._is_connected = False

    @staticmethod
    def _decode_header_str(header_val: str) -> str:
        """Decodes RFC 2047 MIME encoded headers safely."""
        if not header_val:
            return ""
        try:
            decoded_header = email.header.decode_header(header_val)
            return str(email.header.make_header(decoded_header))
        except Exception:
            return header_val

    @staticmethod
    def _clean_header(val: str) -> str:
        if not val:
            return ""
        return val.strip().replace("\r", "").replace("\n", "")

    @classmethod
    def _parse_single_address(cls, raw: str) -> EmailAddress:
        clean = cls._clean_header(raw)
        parsed = email.utils.parseaddr(clean)
        display_name = cls._decode_header_str(parsed[0])
        email_addr = parsed[1].lower().strip()
        domain = email_addr.split("@")[-1] if "@" in email_addr else ""
        return EmailAddress(raw=clean, email=email_addr, domain=domain, name=display_name)

    @classmethod
    def _parse_address_list(cls, raw: str) -> List[EmailAddress]:
        if not raw:
            return []
        addresses: List[EmailAddress] = []
        parsed_list = email.utils.getaddresses([raw])
        for name, addr in parsed_list:
            clean_name = cls._decode_header_str(name)
            clean_addr = addr.lower().strip()
            if clean_addr:
                domain = clean_addr.split("@")[-1] if "@" in clean_addr else ""
                addresses.append(EmailAddress(
                    raw=f"{clean_name} <{clean_addr}>" if clean_name else clean_addr,
                    email=clean_addr,
                    domain=domain,
                    name=clean_name
                ))
        return addresses

    @staticmethod
    def _decode_payload(payload: bytes, charset: str) -> str:
        encodings_to_try = [charset, "utf-8", "latin1", "windows-1252"]
        for enc in encodings_to_try:
            try:
                return payload.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue
        return payload.decode("utf-8", errors="replace")
