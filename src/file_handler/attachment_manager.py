"""Attachment downloader and manager with security validation, consistent renaming, and quarantine handling."""

import os
import zipfile
import io
from typing import List, Tuple, Optional
from src.security.validator import AttachmentValidator, ValidationResult
from src.security.sanitizer import sanitize_filename
from src.email_receiver.models import AttachmentInfo


class AttachmentManager:
    """
    Handles attachment processing: validation, renaming, safe saving,
    permission enforcement, and quarantine handling.
    """

    def __init__(
        self,
        validator: AttachmentValidator,
        file_permissions: int = 0o640,
        dir_permissions: int = 0o750,
        extract_zips: bool = False
    ):
        self.validator = validator
        self.file_permissions = file_permissions
        self.dir_permissions = dir_permissions
        self.extract_zips = extract_zips

    def process_attachments(
        self,
        raw_attachments: List[AttachmentInfo],
        job_id: str,
        job_dir: str,
        quarantine_dir: str
    ) -> Tuple[List[AttachmentInfo], List[AttachmentInfo]]:
        """
        Processes, validates, and saves all attachments for an enquiry.
        Returns a tuple of (saved_valid_attachments, quarantined_attachments).
        """
        saved_list: List[AttachmentInfo] = []
        quarantined_list: List[AttachmentInfo] = []

        attachments_dir = os.path.join(job_dir, "attachments")
        os.makedirs(attachments_dir, exist_ok=True)
        os.chmod(attachments_dir, self.dir_permissions)

        os.makedirs(quarantine_dir, exist_ok=True)
        os.chmod(quarantine_dir, self.dir_permissions)

        for index, att in enumerate(raw_attachments, start=1):
            clean_name = sanitize_filename(att.original_filename, fallback=f"attachment_{index}")
            
            # Security validation
            validation: ValidationResult = self.validator.validate(clean_name, att.data)
            att.is_valid = validation.is_valid
            att.validation_reason = validation.reason

            # Consistent naming format: {job_id}_{index:02d}_{clean_name}
            consistent_filename = f"{job_id}_{index:02d}_{clean_name}"
            att.sanitized_filename = consistent_filename

            if validation.is_valid:
                target_path = os.path.join(attachments_dir, consistent_filename)
                self._save_atomic(target_path, att.data, self.file_permissions)
                att.saved_path = target_path

                # If zip extraction is enabled and valid zip
                if self.extract_zips and validation.detected_type == "zip":
                    extracted = self._safe_extract_zip(att.data, job_id, index, attachments_dir)
                    att.extracted_files = extracted

                saved_list.append(att)
            else:
                # Quarantining invalid or dangerous attachment
                att.is_quarantined = True
                quarantine_filename = f"{consistent_filename}.quarantine"
                quarantine_path = os.path.join(quarantine_dir, quarantine_filename)
                
                # Save with strict read-only permissions for owner only (0600)
                self._save_atomic(quarantine_path, att.data, 0o600)
                att.saved_path = quarantine_path
                quarantined_list.append(att)

        return saved_list, quarantined_list

    def _save_atomic(self, target_path: str, data: bytes, permissions: int) -> None:
        """Writes data to a temporary file before renaming to ensure atomic write."""
        temp_path = f"{target_path}.tmp.{os.getpid()}"
        with open(temp_path, "wb") as f:
            f.write(data)
        os.chmod(temp_path, permissions)
        os.replace(temp_path, target_path)

    def _safe_extract_zip(
        self,
        data: bytes,
        job_id: str,
        zip_index: int,
        parent_dir: str
    ) -> List[str]:
        """Safely unpacks ZIP contents into a dedicated subfolder."""
        extracted_paths: List[str] = []
        zip_folder_name = f"{job_id}_{zip_index:02d}_unpacked"
        extract_dir = os.path.join(parent_dir, zip_folder_name)
        os.makedirs(extract_dir, exist_ok=True)
        os.chmod(extract_dir, self.dir_permissions)

        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                for member in zf.infolist():
                    if member.is_dir():
                        continue
                    clean_member_name = sanitize_filename(member.filename)
                    dest_file = os.path.join(extract_dir, clean_member_name)
                    
                    member_data = zf.read(member.filename)
                    # Validate extracted file
                    member_val = self.validator.validate(clean_member_name, member_data)
                    if member_val.is_valid:
                        self._save_atomic(dest_file, member_data, self.file_permissions)
                        extracted_paths.append(dest_file)
        except Exception:
            pass  # Non-fatal error during zip expansion

        return extracted_paths
