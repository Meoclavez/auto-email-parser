"""Filename and identifier sanitization utility against path traversal, RLO spoofing, and injection attacks."""

import re
import unicodedata
from typing import Optional, Union, Any

WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
}

COMMON_EMAIL_PROVIDERS = {
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.uk", "hotmail.com",
    "outlook.com", "live.com", "icloud.com", "protonmail.com", "aol.com", "mail.com"
}


def sanitize_filename(filename: str, fallback: str = "attachment.dat", max_length: int = 150) -> str:
    """Sanitizes attachment filename against path traversal, RLO spoofing, and reserved device names."""
    if not filename or not str(filename).strip():
        return fallback

    clean = str(filename).strip()

    # If only whitespace + extension (e.g. "   .pdf")
    if clean.startswith(".") and len(clean.split(".")) == 2:
        return f"attachment{clean}"

    # Extract basename stripping path traversal in POSIX and Windows formats
    clean = clean.replace("\\", "/")
    clean = clean.split("/")[-1]

    # Normalize unicode
    clean = unicodedata.normalize("NFKC", clean)

    # Replace bad characters with underscore, preserve dots and hashes
    clean = re.sub(r'[:\*\?<>\|]', '_', clean)
    clean = re.sub(r'[\x00-\x1f\x7f\u200e\u200f\u202a-\u202e]', '', clean)
    clean = re.sub(r'_+\.', '.', clean)
    clean = clean.strip(". ")

    if not clean:
        return fallback

    # Check for reserved DOS device names
    base_name = clean.split(".")[0].upper()
    if base_name in WINDOWS_RESERVED_NAMES:
        parts = clean.split(".", 1)
        ext = f".{parts[1]}" if len(parts) > 1 else ""
        clean = f"{parts[0]}_file{ext}"

    if len(clean) > max_length:
        parts = clean.rsplit(".", 1)
        if len(parts) == 2:
            ext = "." + parts[1][:10]
            clean = parts[0][:max_length - len(ext)] + ext
        else:
            clean = clean[:max_length]

    return clean or fallback


def sanitize_identifier(identifier: str, max_length: int = 50) -> str:
    """Sanitizes customer names or enquiry references for folder naming."""
    if not identifier or not str(identifier).strip():
        return "client"

    clean = unicodedata.normalize("NFKD", str(identifier)).encode("ascii", "ignore").decode("ascii")
    clean = re.sub(r"[^\w\s-]", "", clean).strip().lower()
    clean = re.sub(r"[-\s]+", "-", clean)
    clean = clean.strip("-")

    return clean[:max_length] if clean else "client"


def extract_client_identifier(sender: Union[str, Any], display_name: Optional[str] = None) -> str:
    """Extracts a clean client identifier slug from an EmailAddress object or email string."""
    raw_addr = ""
    name = ""
    domain = ""

    if hasattr(sender, "email"):
        raw_addr = sender.email or ""
        name = getattr(sender, "name", "") or getattr(sender, "display_name", "")
        domain = getattr(sender, "domain", "")
    elif isinstance(sender, str):
        raw_addr = sender
        name = display_name or ""

    if not domain and "@" in raw_addr:
        domain = raw_addr.split("@")[-1].lower()

    if domain and domain not in COMMON_EMAIL_PROVIDERS:
        parts = domain.split(".")
        if len(parts) >= 2:
            return sanitize_identifier(parts[0], max_length=30)

    if name:
        clean_name = sanitize_identifier(name, max_length=30)
        if clean_name and clean_name != "client":
            return clean_name

    if raw_addr and "@" in raw_addr:
        user_part = raw_addr.split("@")[0]
        return sanitize_identifier(user_part, max_length=30)

    return "client"


def extract_job_reference(subject: str) -> Optional[str]:
    """Attempts to extract job/quote reference containing alphanumeric ID or numbers from subject."""
    if not subject:
        return None
    
    # Priority 1: Direct hashtag or bracketed references (e.g. #JOB994, [REF-123])
    m = re.search(r"#\s*([a-z0-9-_]{3,20})", subject, re.IGNORECASE)
    if m:
        return sanitize_identifier(m.group(1), max_length=20)

    m = re.search(r"\[([a-z0-9-_]{3,20})\]", subject, re.IGNORECASE)
    if m:
        return sanitize_identifier(m.group(1), max_length=20)

    # Priority 2: Keyword prefix followed by number/reference (e.g. Quote RFQ-88219)
    m = re.search(r"(?:rfq|quote|job|order|po|ref|enquiry)[\s:#_-]+(?:rfq|quote|job|order|po|ref|enquiry)?[\s:#_-]*([a-z0-9-_]*\d+[a-z0-9-_]*)", subject, re.IGNORECASE)
    if m:
        candidate = m.group(1).lower()
        if candidate not in ("quote", "rfq", "job", "order", "enquiry", "for", "the"):
            return sanitize_identifier(candidate, max_length=20)

    return None
