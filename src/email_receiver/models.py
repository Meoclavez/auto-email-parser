"""Data models for email intake, attachment metadata, and processing manifests."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any
import hashlib


@dataclass
class EmailAddress:
    """Represents a parsed email address with name and domain."""
    raw: str
    name: str = ""
    email: str = ""
    domain: str = ""

    @classmethod
    def parse(cls, raw_addr: str) -> "EmailAddress":
        if not raw_addr:
            return cls(raw="")
        raw_str = raw_addr.strip()
        name = ""
        email = raw_str
        if "<" in raw_str and ">" in raw_str:
            parts = raw_str.split("<", 1)
            name = parts[0].strip().strip('"\'')
            email = parts[1].split(">", 1)[0].strip()
        
        email = email.lower()
        domain = email.split("@", 1)[1] if "@" in email else ""
        return cls(raw=raw_str, name=name, email=email, domain=domain)


@dataclass
class AttachmentInfo:
    """Represents an attachment extracted from an email."""
    original_filename: str
    sanitized_filename: str
    content_type: str
    size_bytes: int
    data: bytes = field(repr=False)
    sha256: str = ""
    is_valid: bool = True
    is_quarantined: bool = False
    validation_reason: str = ""
    saved_path: Optional[str] = None
    extracted_files: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.sha256 and self.data:
            self.sha256 = hashlib.sha256(self.data).hexdigest()
        if self.data:
            self.size_bytes = len(self.data)


@dataclass
class EmailMessage:
    """Represents a fully parsed email ready for filtering and job creation."""
    uid: str
    message_id: str
    subject: str
    sender: EmailAddress
    to_recipients: List[EmailAddress] = field(default_factory=list)
    cc_recipients: List[EmailAddress] = field(default_factory=list)
    date_str: str = ""
    date_dt: Optional[datetime] = None
    body_plain: str = ""
    body_html: str = ""
    attachments: List[AttachmentInfo] = field(default_factory=list)
    raw_headers: Dict[str, str] = field(default_factory=dict)
    folder: str = "INBOX"

    @property
    def all_recipient_emails(self) -> List[str]:
        return [r.email for r in self.to_recipients + self.cc_recipients if r.email]


@dataclass
class FilterResult:
    """Outcome of evaluating email against filter criteria."""
    is_match: bool
    matched_rules: List[str] = field(default_factory=list)
    rejection_reasons: List[str] = field(default_factory=list)


@dataclass
class JobManifest:
    """Audit log manifest stored in JSON alongside the email markdown."""
    job_id: str
    client_id: str
    message_id: str
    subject: str
    sender: str
    sender_domain: str
    recipients: List[str]
    received_date: str
    processed_date: str
    status: str
    filter_matches: List[str]
    email_md_file: str
    attachments: List[Dict[str, Any]] = field(default_factory=list)
    quarantined_attachments: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "client_id": self.client_id,
            "message_id": self.message_id,
            "subject": self.subject,
            "sender": self.sender,
            "sender_domain": self.sender_domain,
            "recipients": self.recipients,
            "received_date": self.received_date,
            "processed_date": self.processed_date,
            "status": self.status,
            "filter_matches": self.filter_matches,
            "email_md_file": self.email_md_file,
            "attachments": self.attachments,
            "quarantined_attachments": self.quarantined_attachments,
            "errors": self.errors,
        }
