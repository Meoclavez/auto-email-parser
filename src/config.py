"""Application configuration loader with YAML and environment variable overrides."""

import os
import re
from dataclasses import dataclass, field
from typing import List, Set, Optional, Dict, Any
import yaml


@dataclass
class IMAPConfig:
    server: str = "imap.example.com"
    port: int = 993
    username: str = ""
    password: str = ""
    use_ssl: bool = True
    mailbox: str = "INBOX"
    poll_interval_seconds: int = 60
    use_idle: bool = True
    mark_as_read: bool = True
    max_emails_per_batch: int = 50
    connection_timeout: int = 30
    max_retry_backoff: int = 60


@dataclass
class FilterConfig:
    allowed_sender_domains: List[str] = field(default_factory=list)
    blocked_sender_domains: List[str] = field(default_factory=list)
    required_subject_keywords: List[str] = field(default_factory=list)
    excluded_subject_keywords: List[str] = field(default_factory=list)
    subject_regex: Optional[str] = None
    intake_addresses: List[str] = field(default_factory=list)
    require_attachments: bool = False
    match_all_keywords: bool = False


@dataclass
class StorageConfig:
    base_dir: str = "storage/jobs"
    quarantine_dir: str = "storage/quarantine"
    database_path: str = "storage/email_jobs.db"
    job_id_prefix: str = "JOB"
    file_permissions: int = 0o640
    dir_permissions: int = 0o750
    min_free_disk_mb: int = 500


@dataclass
class SecurityConfig:
    max_file_size_mb: int = 50
    max_zip_uncompressed_mb: int = 150
    max_zip_entries: int = 100
    allowed_extensions: List[str] = field(default_factory=lambda: [
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".txt",
        ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff",
        ".dxf", ".dwg", ".step", ".stp", ".iges", ".igs", ".stl",
        ".zip", ".7z", ".tar", ".gz"
    ])
    allow_zip_archives: bool = True


@dataclass
class AppConfig:
    imap: IMAPConfig = field(default_factory=IMAPConfig)
    filters: FilterConfig = field(default_factory=FilterConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    log_level: str = "INFO"

    @classmethod
    def load_from_yaml(cls, path: str = "config/config.yaml") -> "AppConfig":
        """Loads configuration from YAML file and applies environment overrides."""
        config_data: Dict[str, Any] = {}
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
                # Substitute ${VAR_NAME} environment variables in YAML
                content = cls._substitute_env_vars(content)
                config_data = yaml.safe_load(content) or {}

        # Also load from root .env if present
        cls._load_dotenv()

        imap_data = config_data.get("imap", {})
        filter_data = config_data.get("filters", {})
        storage_data = config_data.get("storage", {})
        security_data = config_data.get("security", {})

        # Environment variable overrides
        imap_server = os.getenv("IMAP_SERVER", imap_data.get("server", "imap.example.com"))
        imap_port = int(os.getenv("IMAP_PORT", imap_data.get("port", 993)))
        imap_user = os.getenv("IMAP_USER", os.getenv("IMAP_USERNAME", imap_data.get("username", "")))
        imap_pass = os.getenv("IMAP_PASSWORD", imap_data.get("password", ""))
        imap_ssl = os.getenv("IMAP_USE_SSL", str(imap_data.get("use_ssl", True))).lower() in ("true", "1", "yes")
        imap_mailbox = os.getenv("IMAP_MAILBOX", imap_data.get("mailbox", "INBOX"))
        poll_interval = int(os.getenv("POLL_INTERVAL", imap_data.get("poll_interval_seconds", 60)))

        storage_base = os.getenv("STORAGE_BASE_DIR", storage_data.get("base_dir", "storage/jobs"))
        db_path = os.getenv("DATABASE_PATH", storage_data.get("database_path", "storage/email_jobs.db"))

        # Permissions parsing
        file_perm_str = str(storage_data.get("file_permissions", "0640"))
        dir_perm_str = str(storage_data.get("dir_permissions", "0750"))
        file_perm = int(file_perm_str, 8) if file_perm_str.startswith("0") else int(file_perm_str)
        dir_perm = int(dir_perm_str, 8) if dir_perm_str.startswith("0") else int(dir_perm_str)

        return cls(
            imap=IMAPConfig(
                server=imap_server,
                port=imap_port,
                username=imap_user,
                password=imap_pass,
                use_ssl=imap_ssl,
                mailbox=imap_mailbox,
                poll_interval_seconds=poll_interval,
                use_idle=imap_data.get("use_idle", True),
                mark_as_read=imap_data.get("mark_as_read", True),
                max_emails_per_batch=imap_data.get("max_emails_per_batch", 50),
                connection_timeout=imap_data.get("connection_timeout", 30),
                max_retry_backoff=imap_data.get("max_retry_backoff", 60)
            ),
            filters=FilterConfig(
                allowed_sender_domains=filter_data.get("allowed_sender_domains", []),
                blocked_sender_domains=filter_data.get("blocked_sender_domains", []),
                required_subject_keywords=filter_data.get("required_subject_keywords", []),
                excluded_subject_keywords=filter_data.get("excluded_subject_keywords", []),
                subject_regex=filter_data.get("subject_regex"),
                intake_addresses=filter_data.get("intake_addresses", []),
                require_attachments=filter_data.get("require_attachments", False),
                match_all_keywords=filter_data.get("match_all_keywords", False)
            ),
            storage=StorageConfig(
                base_dir=storage_base,
                quarantine_dir=storage_data.get("quarantine_dir", "storage/quarantine"),
                database_path=db_path,
                job_id_prefix=storage_data.get("job_id_prefix", "JOB"),
                file_permissions=file_perm,
                dir_permissions=dir_perm,
                min_free_disk_mb=storage_data.get("min_free_disk_mb", 500)
            ),
            security=SecurityConfig(
                max_file_size_mb=security_data.get("max_file_size_mb", 50),
                max_zip_uncompressed_mb=security_data.get("max_zip_uncompressed_mb", 150),
                max_zip_entries=security_data.get("max_zip_entries", 100),
                allowed_extensions=security_data.get("allowed_extensions", SecurityConfig().allowed_extensions),
                allow_zip_archives=security_data.get("allow_zip_archives", True)
            ),
            log_level=os.getenv("LOG_LEVEL", config_data.get("log_level", "INFO"))
        )

    @staticmethod
    def _substitute_env_vars(text: str) -> str:
        """Replaces ${VAR:-default} or ${VAR} with environment variable values."""
        pattern = re.compile(r'\$\{([A-Za-z0-9_]+)(?::-([^}]*))?\}')

        def replace_match(match):
            var_name = match.group(1)
            default_val = match.group(2) if match.group(2) is not None else ""
            return os.getenv(var_name, default_val)

        return pattern.sub(replace_match, text)

    @staticmethod
    def _load_dotenv(path: str = ".env"):
        """Simple .env loader if file exists."""
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"\'')
                    if k and k not in os.environ:
                        os.environ[k] = v
