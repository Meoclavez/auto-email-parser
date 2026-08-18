"""Service orchestrator managing the daemon lifecycle, graceful shutdown, pre-flight checks, and email pipeline."""

import os
import time
import signal
import shutil
import logging
from typing import Dict, Any, Optional

from src.config import AppConfig
from src.storage.state_db import StateDatabase
from src.security.validator import AttachmentValidator
from src.file_handler.attachment_manager import AttachmentManager
from src.file_handler.markdown_writer import EmailMarkdownWriter
from src.storage.job_manager import JobManager
from src.email_receiver.filters import EmailFilter
from src.email_receiver.imap_client import IMAPReceiver
from src.email_receiver.models import EmailMessage

logger = logging.getLogger("EmailParser.Service")


class EmailParserService:
    """
    Main orchestration service for the email parser and downloader.
    """

    def __init__(self, config: AppConfig):
        self.config = config
        self._running = False

        # Initialize components
        self.state_db = StateDatabase(self.config.storage.database_path)
        self.validator = AttachmentValidator(
            allowed_extensions=set(self.config.security.allowed_extensions),
            max_file_size_mb=self.config.security.max_file_size_mb,
            max_zip_uncompressed_mb=self.config.security.max_zip_uncompressed_mb,
            max_zip_entries=self.config.security.max_zip_entries,
            allow_zip_archives=self.config.security.allow_zip_archives
        )
        self.attachment_manager = AttachmentManager(
            validator=self.validator,
            file_permissions=self.config.storage.file_permissions,
            dir_permissions=self.config.storage.dir_permissions,
            extract_zips=False
        )
        self.markdown_writer = EmailMarkdownWriter()
        self.job_manager = JobManager(
            config=self.config.storage,
            state_db=self.state_db,
            attachment_manager=self.attachment_manager,
            markdown_writer=self.markdown_writer
        )
        self.filter_engine = EmailFilter(self.config.filters)
        self.imap_client = IMAPReceiver(self.config.imap)

        # Set up signal handlers for graceful shutdown
        self._setup_signals()

    def _setup_signals(self):
        """Registers handlers for SIGINT and SIGTERM."""
        signal.signal(signal.SIGINT, self._handle_shutdown_signal)
        signal.signal(signal.SIGTERM, self._handle_shutdown_signal)

    def _handle_shutdown_signal(self, signum, frame):
        logger.info(f"Received termination signal ({signum}). Initiating graceful shutdown...")
        self._running = False

    def pre_flight_checks(self) -> bool:
        """Verifies environment, disk space, and filesystem permissions."""
        logger.info("Executing pre-flight health checks...")

        # 1. Base storage directory writable check
        base_dir = os.path.abspath(self.config.storage.base_dir)
        try:
            os.makedirs(base_dir, exist_ok=True)
            test_file = os.path.join(base_dir, f".write_test_{os.getpid()}")
            with open(test_file, "w") as f:
                f.write("ok")
            os.remove(test_file)
            logger.info(f"Storage directory writable: {base_dir}")
        except Exception as e:
            logger.error(f"Storage directory is NOT writable ({base_dir}): {e}")
            return False

        # 2. Disk space check
        try:
            total, used, free = shutil.disk_usage(base_dir)
            free_mb = free / (1024 * 1024)
            if free_mb < self.config.storage.min_free_disk_mb:
                logger.error(f"Insufficient disk space: {free_mb:.1f}MB available, minimum required is {self.config.storage.min_free_disk_mb}MB")
                return False
            logger.info(f"Disk space check passed: {free_mb:.1f}MB free")
        except Exception as e:
            logger.warning(f"Could not verify disk usage: {e}")

        # 3. Database connectivity
        try:
            stats = self.state_db.get_stats()
            logger.info(f"State Database initialized. Current records: {stats.get('TOTAL', 0)}")
        except Exception as e:
            logger.error(f"Failed to access state database: {e}")
            return False

        return True

    def process_single_email(self, email: EmailMessage) -> Optional[Dict[str, Any]]:
        """
        Processes one email through filtering, job creation, and state updates.
        Returns job info dict if created, None if ignored or skipped.
        """
        logger.info(f"Processing email: Subject='{email.subject}', From='{email.sender.raw}', UID='{email.uid}'")

        # Step 1: Check if already processed (Idempotency)
        if self.state_db.is_message_processed(email.message_id):
            logger.info(f"Skipping already processed message ID: {email.message_id}")
            return None

        # Record start
        self.state_db.record_start(
            message_id=email.message_id,
            uid=email.uid,
            sender=email.sender.raw,
            subject=email.subject
        )

        # Step 2: Evaluate filters
        filter_res = self.filter_engine.evaluate(email)
        if not filter_res.is_match:
            reason_str = "; ".join(filter_res.rejection_reasons)
            logger.info(f"Email skipped by filter: {reason_str}")
            self.state_db.record_ignored(
                message_id=email.message_id,
                uid=email.uid,
                sender=email.sender.raw,
                subject=email.subject,
                reason=reason_str
            )
            if self.config.imap.mark_as_read and email.uid:
                self.imap_client.mark_as_read(email.uid)
            return None

        # Step 3: Create Job Directory & Attachments
        try:
            job_result = self.job_manager.create_job(email, filter_res)
            logger.info(
                f"Job Created Successfully: {job_result['job_id']} in '{job_result['job_dir']}' "
                f"({job_result['saved_attachments_count']} saved, {job_result['quarantined_attachments_count']} quarantined)"
            )
            
            # Step 4: Mark email read on IMAP server
            if self.config.imap.mark_as_read and email.uid:
                self.imap_client.mark_as_read(email.uid)

            return job_result

        except Exception as e:
            logger.error(f"Failed to process email into job (Message-ID: {email.message_id}): {e}", exc_info=True)
            self.state_db.record_failure(email.message_id, str(e))
            return None

    def process_once(self) -> int:
        """
        Performs a single polling cycle, processing all available unread emails.
        Returns the number of jobs created.
        """
        if not self.pre_flight_checks():
            return 0

        logger.info("Starting single-pass intake cycle...")
        emails = self.imap_client.fetch_unread_emails()
        jobs_created = 0

        for email_msg in emails:
            res = self.process_single_email(email_msg)
            if res and res.get("status") == "SUCCESS":
                jobs_created += 1

        self.imap_client.close()
        logger.info(f"Intake cycle complete. Created {jobs_created} job(s) from {len(emails)} unread email(s).")
        return jobs_created

    def run_daemon(self):
        """
        Runs continuous background monitoring loop with poll interval and error recovery.
        """
        if not self.pre_flight_checks():
            logger.error("Pre-flight checks failed. Daemon will not start.")
            return

        self._running = True
        logger.info(f"Starting Email Parser Daemon (Poll interval: {self.config.imap.poll_interval_seconds}s)...")

        while self._running:
            try:
                emails = self.imap_client.fetch_unread_emails()
                for email_msg in emails:
                    if not self._running:
                        break
                    self.process_single_email(email_msg)

            except Exception as e:
                logger.error(f"Unexpected error in daemon loop: {e}", exc_info=True)

            # Sleep in 1-second increments to respond promptly to shutdown signals
            for _ in range(max(1, self.config.imap.poll_interval_seconds)):
                if not self._running:
                    break
                time.sleep(1)

        self.imap_client.close()
        logger.info("Email Parser Daemon stopped gracefully.")
