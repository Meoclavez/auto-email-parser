"""Attachment security validator with file extension whitelisting, magic byte signature sniffing, and zip bomb inspection."""

import io
import os
import zipfile
import logging
from dataclasses import dataclass
from typing import Set, Tuple, Optional, Dict

logger = logging.getLogger("EmailParser.Validator")


@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    is_quarantined: bool
    reason: str
    detected_type: Optional[str] = None
    sanitized_extension: Optional[str] = None


MAGIC_SIGNATURES: Dict[bytes, Tuple[str, str]] = {
    b"%PDF-": ("application/pdf", "pdf"),
    b"\x89PNG\r\n\x1a\n": ("image/png", "png"),
    b"\xff\xd8\xff": ("image/jpeg", "jpeg"),
    b"GIF87a": ("image/gif", "gif"),
    b"GIF89a": ("image/gif", "gif"),
    b"II*\x00": ("image/tiff", "tiff_le"),
    b"MM\x00*": ("image/tiff", "tiff_be"),
    b"PK\x03\x04": ("application/zip", "zip"),
    b"PK\x05\x06": ("application/zip", "zip_empty"),
    b"PK\x07\x08": ("application/zip", "zip_spanned"),
}

EXECUTABLE_SIGNATURES = {
    b"MZ": "Windows Executable/DLL (MZ Header)",
    b"\x7fELF": "Linux Executable (ELF Header)",
    b"\xca\xfe\xba\xbe": "Java Class / Mach-O Binary",
    b"#!": "Shell Script / Executable Hashbang",
}

DEFAULT_ALLOWED_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".txt", ".csv", ".rtf",
    ".jpg", ".jpeg", ".png", ".gif", ".tif", ".tiff", ".bmp",
    ".dxf", ".dwg", ".step", ".stp", ".iges", ".igs", ".sat", ".x_t", ".x_b",
    ".zip"
}


class AttachmentValidator:
    """Validates attachment integrity and inspects signatures."""

    def __init__(
        self,
        allowed_extensions: Optional[Set[str]] = None,
        max_file_size_mb: int = 50,
        max_zip_uncompressed_mb: int = 200,
        max_zip_entries: int = 500,
        allow_zip_archives: bool = True
    ):
        self.allowed_extensions = {ext.lower() for ext in (allowed_extensions or DEFAULT_ALLOWED_EXTENSIONS)}
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024
        self.max_zip_uncompressed_bytes = max_zip_uncompressed_mb * 1024 * 1024
        self.max_zip_entries = max_zip_entries
        self.allow_zip_archives = allow_zip_archives

    def validate(self, filename: str, data: bytes) -> ValidationResult:
        """Validates an attachment by extension, size, magic signature, and executable header."""
        if not data:
            return ValidationResult(is_valid=False, is_quarantined=False, reason="File is empty (0 bytes).")

        if len(data) > self.max_file_size_bytes:
            return ValidationResult(
                is_valid=False,
                is_quarantined=True,
                reason=f"File exceeds maximum allowed size of {self.max_file_size_bytes} bytes ({len(data) / (1024*1024):.1f}MB)."
            )

        _, ext = os.path.splitext(filename.lower())
        if not ext or ext not in self.allowed_extensions:
            return ValidationResult(
                is_valid=False,
                is_quarantined=True,
                reason=f"Forbidden extension: '{ext}' is not permitted by security policy.",
                sanitized_extension=ext
            )

        for sig, desc in EXECUTABLE_SIGNATURES.items():
            if data.startswith(sig):
                return ValidationResult(
                    is_valid=False,
                    is_quarantined=True,
                    reason=f"Executable binary signature detected: {desc}",
                    sanitized_extension=ext
                )

        detected_type = self._sniff_magic_type(data, ext)

        if ext == ".zip":
            if not self.allow_zip_archives:
                return ValidationResult(is_valid=False, is_quarantined=True, reason="ZIP archives disallowed.", sanitized_extension=ext)
            is_valid, reason = self._inspect_zip_archive(data)
            return ValidationResult(
                is_valid=is_valid,
                is_quarantined=not is_valid,
                reason=reason,
                detected_type="zip",
                sanitized_extension=ext
            )

        return ValidationResult(
            is_valid=True,
            is_quarantined=False,
            reason="Validation passed.",
            detected_type=detected_type,
            sanitized_extension=ext
        )

    def _sniff_magic_type(self, data: bytes, ext: str) -> str:
        for sig, (_, type_name) in MAGIC_SIGNATURES.items():
            if data.startswith(sig):
                return type_name

        if ext == ".dxf" and (b"SECTION" in data[:512] or b"HEADER" in data[:512]):
            return "cad_dxf"
        if ext in (".step", ".stp") and b"ISO-10303-21" in data[:512]:
            return "cad_step"
        if ext in (".iges", ".igs") and len(data) >= 80 and data[72:73] in (b"S", b"G", b"D", b"P", b"T"):
            return "cad_iges"

        return "generic_binary"

    def _inspect_zip_archive(self, data: bytes) -> Tuple[bool, str]:
        try:
            with zipfile.ZipFile(io.BytesIO(data), 'r') as zf:
                infos = zf.infolist()
                if len(infos) > self.max_zip_entries:
                    return False, f"ZIP bomb trap: contains {len(infos)} files (max {self.max_zip_entries})."

                total_uncompressed = 0
                for info in infos:
                    total_uncompressed += info.file_size
                    if total_uncompressed > self.max_zip_uncompressed_bytes:
                        return False, f"ZIP bomb trap: uncompressed size exceeds {self.max_zip_uncompressed_bytes / (1024*1024):.1f}MB."

                    if ".." in info.filename or info.filename.startswith(("/", "\\")):
                        return False, f"ZIP path traversal trap in member: {info.filename}"

                    _, member_ext = os.path.splitext(info.filename.lower())
                    if member_ext in (".exe", ".bat", ".cmd", ".sh", ".vbs", ".ps1", ".dll", ".so", ".elf"):
                        return False, f"ZIP contains forbidden executable file: {info.filename}"

            return True, "Valid ZIP archive"
        except zipfile.BadZipFile:
            return False, "Corrupted ZIP archive."
        except Exception as e:
            return False, f"ZIP inspection error: {str(e)}"
