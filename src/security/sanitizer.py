"""Security utilities for filename sanitization, path traversal mitigation, and identifier extraction."""

import os
import re
import unicodedata
from typing import Optional, List
from src.email_receiver.models import EmailAddress

# Reserved filenames on Windows/DOS systems
RESERVED_DEVICE_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
}

# Dangerous characters in filenames across POSIX and Windows filesystems
DANGEROUS_CHARS_REGEX = re.compile(r'[\0/\\:\*\?"<>\|;\$&`\'\n\r\t]')


def sanitize_filename(
    raw_name: str,
    max_length: int = 150,
    fallback: str = "attachment"
) -> str:
    """
    Sanitizes a filename to prevent Path Traversal, Null Byte Injection,
    and special shell character exploits.
    """
    if not raw_name or not isinstance(raw_name, str):
        return f"{fallback}.dat"

    # Step 1: Strip leading/trailing whitespaces and null bytes
    cleaned = raw_name.replace('\0', '').strip()
    if not cleaned:
        return f"{fallback}.dat"

    # Step 2: Remove any path component (POSIX & Windows)
    cleaned = os.path.basename(cleaned)
    if '\\' in cleaned:
        cleaned = cleaned.split('\\')[-1]
    if '/' in cleaned:
        cleaned = cleaned.split('/')[-1]

    # Step 3: Normalize Unicode characters (NFKD form)
    cleaned = unicodedata.normalize('NFKD', cleaned)

    # Step 4: Handle pure extension input like '.pdf' or '.dxf'
    if cleaned.startswith('.') and cleaned.count('.') == 1:
        ext_part = cleaned
        name_part = fallback
    else:
        name_part, ext_part = os.path.splitext(cleaned)
    
    # Step 5: Replace dangerous characters with underscores
    name_part = DANGEROUS_CHARS_REGEX.sub('_', name_part)
    ext_part = DANGEROUS_CHARS_REGEX.sub('_', ext_part)

    # Step 6: Collapse multiple underscores or spaces
    name_part = re.sub(r'[\s_]+', '_', name_part).strip(' ._-')
    ext_part = re.sub(r'[\s_]+', '', ext_part).strip(' ')

    # Step 7: Handle empty base name or empty extension
    if not name_part:
        name_part = fallback

    if not ext_part:
        ext_part = ".dat" if name_part == fallback else ""

    if name_part.upper() in RESERVED_DEVICE_NAMES:
        name_part = f"{name_part}_file"

    # Step 8: Enforce max length while preserving extension
    max_name_len = max(10, max_length - len(ext_part))
    if len(name_part) > max_name_len:
        name_part = name_part[:max_name_len].rstrip(' ._-')

    sanitized = f"{name_part}{ext_part}"
    return sanitized if sanitized else f"{fallback}.dat"


def sanitize_identifier(
    name: str,
    max_length: int = 50,
    fallback: str = "client"
) -> str:
    """
    Converts a client name or job text into a clean alphanumeric slug
    suitable for folder and file names.
    """
    if not name or not isinstance(name, str):
        return fallback

    # Normalize unicode
    cleaned = unicodedata.normalize('NFKD', name)
    cleaned = cleaned.encode('ascii', 'ignore').decode('ascii')
    
    # Replace non-alphanumeric with hyphens
    cleaned = re.sub(r'[^a-zA-Z0-9_-]+', '-', cleaned).strip('-_')
    cleaned = re.sub(r'-+', '-', cleaned).lower()

    if not cleaned:
        return fallback

    if cleaned.upper() in RESERVED_DEVICE_NAMES:
        cleaned = f"{cleaned}-corp"

    return cleaned[:max_length].rstrip('-_')


def extract_client_identifier(sender: EmailAddress, subject: str = "") -> str:
    """
    Extracts a meaningful client identifier from the sender information.
    Prioritizes domain name (excluding common public email providers like gmail/yahoo/outlook)
    or sender name slug.
    """
    public_providers = {
        "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com",
        "proton.me", "protonmail.com", "aol.com", "mail.com", "zoho.com"
    }

    if sender.domain and sender.domain not in public_providers:
        # e.g., acme-engineering.co.uk -> acme-engineering
        domain_parts = sender.domain.split(".")
        if len(domain_parts) >= 2:
            return sanitize_identifier(domain_parts[0])

    if sender.name:
        return sanitize_identifier(sender.name)

    if sender.email:
        local_part = sender.email.split("@")[0]
        return sanitize_identifier(local_part)

    return "unknown-client"


def extract_job_reference(
    subject: str,
    patterns: Optional[List[str]] = None
) -> Optional[str]:
    """
    Extracts explicit RFQ/PO/Job reference numbers from the subject line.
    Example: 'RFQ-99238', 'Quote #1042', 'PO: 88412'
    """
    if not subject:
        return None

    # First check explicit hashtags like #JOB994 or #1042
    hash_match = re.search(r'#([A-Za-z0-9_\-]{3,20})', subject)
    if hash_match:
        return sanitize_identifier(hash_match.group(1).strip(), max_length=30)

    default_patterns = [
        # Keyword followed by reference code e.g. RFQ-88219, PO_1204
        r'(?:RFQ|ENQ|JOB|QUOTE|PO|PROJECT|ORDER)[\s#:_\-\/]+([A-Za-z0-9_\-]*[0-9]+[A-Za-z0-9_\-]*)',
        r'(?:RFQ|ENQ|JOB|QUOTE|PO)[\s#:_\-\/]+([A-Za-z0-9_\-]+)',
    ]
    regex_list = patterns or default_patterns

    for pat in regex_list:
        match = re.search(pat, subject, re.IGNORECASE)
        if match:
            raw_ref = match.group(1).strip()
            cleaned_ref = re.sub(r'^(?:RFQ|ENQ|JOB|QUOTE|PO|PROJECT|ORDER)[\s#:_\-\/]*', '', raw_ref, flags=re.I).strip('-_ ')
            final_ref = cleaned_ref if cleaned_ref else raw_ref
            return sanitize_identifier(final_ref, max_length=30)

    return None
