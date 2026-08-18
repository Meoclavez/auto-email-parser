"""Security validator for file types, magic signatures, archive traps, and size bounds."""

import io
import os
import zipfile
from typing import Tuple, Set, Optional, List
from dataclasses import dataclass

# Dangerous executable / script extensions unconditionally blocked
BLOCKED_EXTENSIONS: Set[str] = {
    ".exe", ".dll", ".so", ".bin", ".scr", ".pif", ".hta", ".cpl", ".msi",
    ".bat", ".cmd", ".sh", ".bash", ".ps1", ".vbs", ".vbe", ".js", ".jse",
    ".wsf", ".wsh", ".jar", ".app", ".dmg", ".pkg", ".iso", ".img", ".deb",
    ".rpm", ".com", ".gadget", ".msp"
}

# Standard allowed extensions for engineering/enquiry attachments
DEFAULT_ALLOWED_EXTENSIONS: Set[str] = {
    # Documents
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".txt", ".rtf",
    # Images
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff", ".webp",
    # CAD / 3D models
    ".dxf", ".dwg", ".step", ".stp", ".iges", ".igs", ".stl", ".sat",
    ".x_t", ".x_b", ".sldprt", ".sldasm", ".ipt", ".iam",
    # Archives
    ".zip", ".7z", ".tar", ".gz"
}


@dataclass
class ValidationResult:
    """Outcome of attachment security validation."""
    is_valid: bool
    is_quarantined: bool
    reason: str
    detected_type: str = "unknown"


class AttachmentValidator:
    """
    Validates email attachments against strict security rules:
    1. Extension whitelist & blacklist check
    2. File magic header signature verification
    3. Maximum file size limits
    4. Safe zip archive inspection (zip bomb and path traversal protection)
    """

    def __init__(
        self,
        allowed_extensions: Optional[Set[str]] = None,
        max_file_size_mb: int = 50,
        max_zip_uncompressed_mb: int = 150,
        max_zip_entries: int = 100,
        allow_zip_archives: bool = True,
    ):
        self.allowed_extensions = {ext.lower() for ext in (allowed_extensions or DEFAULT_ALLOWED_EXTENSIONS)}
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024
        self.max_zip_uncompressed_bytes = max_zip_uncompressed_mb * 1024 * 1024
        self.max_zip_entries = max_zip_entries
        self.allow_zip_archives = allow_zip_archives

    def validate(self, filename: str, data: bytes) -> ValidationResult:
        """Runs full suite of security validations on an attachment."""
        if not data or len(data) == 0:
            return ValidationResult(
                is_valid=False,
                is_quarantined=False,
                reason="Empty file (0 bytes)"
            )

        # 1. Size check
        if len(data) > self.max_file_size_bytes:
            return ValidationResult(
                is_valid=False,
                is_quarantined=True,
                reason=f"File exceeds maximum allowed size ({len(data) / (1024*1024):.1f}MB > {self.max_file_size_bytes / (1024*1024):.1f}MB)"
            )

        _, ext = os.path.splitext(filename.lower())

        # 2. Blocked extensions check
        if ext in BLOCKED_EXTENSIONS:
            return ValidationResult(
                is_valid=False,
                is_quarantined=True,
                reason=f"Forbidden file extension: '{ext}' is explicitly prohibited."
            )

        # 3. Whitelist extensions check
        if self.allowed_extensions and ext not in self.allowed_extensions:
            return ValidationResult(
                is_valid=False,
                is_quarantined=True,
                reason=f"File extension '{ext}' is not in the allowed whitelist."
            )

        # 4. Executable / binary header sniffing (prevent disguised executables)
        if self._is_executable_header(data):
            return ValidationResult(
                is_valid=False,
                is_quarantined=True,
                reason="Executable binary signature detected (e.g., Windows MZ/PE or Linux ELF header) masquerading as another file."
            )

        # 5. File type magic validation
        detected_type = self._sniff_magic_type(data, ext)

        # 6. Archive safety checks for ZIP files
        if ext == ".zip" or detected_type == "zip":
            if not self.allow_zip_archives:
                return ValidationResult(
                    is_valid=False,
                    is_quarantined=True,
                    reason="ZIP archives are disabled in system configuration."
                )
            zip_check = self._inspect_zip_archive(data)
            if not zip_check.is_valid:
                return zip_check

        return ValidationResult(
            is_valid=True,
            is_quarantined=False,
            reason="Validation passed",
            detected_type=detected_type
        )

    def _is_executable_header(self, data: bytes) -> bool:
        """Detects executable headers regardless of file extension."""
        # Windows MZ header (EXE, DLL)
        if len(data) >= 2 and data[:2] == b"MZ":
            return True
        # Linux ELF header
        if len(data) >= 4 and data[:4] == b"\x7fELF":
            return True
        # macOS Mach-O header
        if len(data) >= 4 and data[:4] in (b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf", b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe"):
            return True
        return False

    def _sniff_magic_type(self, data: bytes, ext: str) -> str:
        """Inspects first bytes for known formats."""
        # PDF
        if data.startswith(b"%PDF-"):
            return "pdf"
        # JPEG
        if data.startswith(b"\xff\xd8\xff"):
            return "jpeg"
        # PNG
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return "png"
        # GIF
        if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
            return "gif"
        # TIFF
        if data.startswith(b"II*\x00") or data.startswith(b"MM\x00*"):
            return "tiff"
        # ZIP / Office Open XML (docx, xlsx)
        if data.startswith(b"PK\x03\x04") or data.startswith(b"PK\x05\x06"):
            return "zip"

        # CAD Formats
        # DWG
        if len(data) >= 6 and data[:4] == b"AC10":
            return "cad_dwg"
        
        # DXF (Binary)
        if data.startswith(b"AutoCAD Binary DXF"):
            return "cad_dxf"
        
        if ext in (".dxf", ".step", ".stp", ".iges", ".igs"):
            prefix_text = data[:2048].decode('latin-1', errors='ignore').upper()
            if "ISO-10303-21" in prefix_text or "FILE_DESCRIPTION" in prefix_text or ext in (".step", ".stp"):
                return "cad_step"
            if prefix_text.startswith("S0000001") or "IGES" in prefix_text or ext in (".iges", ".igs"):
                return "cad_iges"
            if "SECTION" in prefix_text or ext == ".dxf":
                return "cad_dxf"

        return "generic_binary"

    def _inspect_zip_archive(self, data: bytes) -> ValidationResult:
        """Safely inspects ZIP archive contents for zip-bomb or traversal attacks."""
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                infolist = zf.infolist()
                
                # Check entry count
                if len(infolist) > self.max_zip_entries:
                    return ValidationResult(
                        is_valid=False,
                        is_quarantined=True,
                        reason=f"Archive contains too many entries ({len(infolist)} > {self.max_zip_entries})"
                    )

                total_uncompressed_size = 0
                for info in infolist:
                    total_uncompressed_size += info.file_size
                    
                    # Check for path traversal in zip entry
                    filename = info.filename
                    if ".." in filename or filename.startswith("/") or filename.startswith("\\"):
                        return ValidationResult(
                            is_valid=False,
                            is_quarantined=True,
                            reason=f"Zip archive contains path traversal entry: '{filename}'"
                        )
                    
                    # Check for blocked extensions inside zip
                    _, entry_ext = os.path.splitext(filename.lower())
                    if entry_ext in BLOCKED_EXTENSIONS:
                        return ValidationResult(
                            is_valid=False,
                            is_quarantined=True,
                            reason=f"Zip archive contains forbidden executable: '{filename}'"
                        )

                # Zip bomb size threshold
                if total_uncompressed_size > self.max_zip_uncompressed_bytes:
                    return ValidationResult(
                        is_valid=False,
                        is_quarantined=True,
                        reason=f"Zip archive uncompressed size ({total_uncompressed_size / (1024*1024):.1f}MB) exceeds limit of {self.max_zip_uncompressed_bytes / (1024*1024):.1f}MB"
                    )

            return ValidationResult(
                is_valid=True,
                is_quarantined=False,
                reason="ZIP archive passed inspection",
                detected_type="zip"
            )
        except zipfile.BadZipFile:
            return ValidationResult(
                is_valid=False,
                is_quarantined=True,
                reason="Corrupted or invalid ZIP archive."
            )
        except Exception as e:
            return ValidationResult(
                is_valid=False,
                is_quarantined=True,
                reason=f"Failed to inspect ZIP archive: {str(e)}"
            )
