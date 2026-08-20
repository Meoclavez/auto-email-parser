"""Service orchestrator with multi-mailbox support, dynamic thread-safe daemon controller, and pre-flight checks."""

import os
import time
import signal
import shutil
import threading
import logging
from typing import Dict, Any, Optional, List

from src.config import AppConfig
from src.storage.state_db import StateDatabase
from src.security.validator import AttachmentValidator
from src.security.encryption import CredentialCipher
from src.file_handler.attachment_manager import AttachmentManager
from src.file_handler.markdown_writer import EmailMarkdownWriter
from src.storage.job_manager import JobManager
from src.email_receiver.filters import EmailFilter
from src.email_receiver.imap_client import IMAPReceiver
from src.email_receiver.mailbox_manager import MailboxManager
from src.email_receiver.models import EmailMessage

logger = logging.getLogger("EmailParser.Service")


class EmailParserService:
    """
    Main orchestration service for the email parser and downloader.
    """

    def __init__(self, config: AppConfig):
        self.config = config
        self._running = False
        self._paused = False
        self._worker_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self.last_sync_timestamp: Optional[str] = None

        # Initialize components
        self.state_db = StateDatabase(self.config.storage.database_path)
        self.cipher = CredentialCipher()
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
        self.mailbox_manager = MailboxManager(self.state_db, self.cipher)
        self.imap_client = IMAPReceiver(self.config.imap)

        # Setup signal handlers if in main thread
        if threading.current_thread() is threading.main_thread():
            self._setup_signals()

    def _setup_signals(self):
        try:
            signal.signal(signal.SIGINT, self._handle_shutdown_signal)
            signal.signal(signal.SIGTERM, self._handle_shutdown_signal)
        except (ValueError, AttributeError):
            pass

    def _handle_shutdown_signal(self, signum, frame):
        logger.info(f"Received termination signal ({signum}). Initiating graceful shutdown...")
        self.stop_daemon()

    def pre_flight_checks(self) -> bool:
        """Verifies environment, disk space, and filesystem permissions."""
        base_dir = os.path.abspath(self.config.storage.base_dir)
        try:
            os.makedirs(base_dir, exist_ok=True)
            test_file = os.path.join(base_dir, f".write_test_{os.getpid()}")
            with open(test_file, "w") as f:
                f.write("ok")
            os.remove(test_file)
        except Exception as e:
            logger.error(f"Storage directory is NOT writable ({base_dir}): {e}")
            return False

        try:
            total, used, free = shutil.disk_usage(base_dir)
            free_mb = free / (1024 * 1024)
            if free_mb < self.config.storage.min_free_disk_mb:
                logger.error(f"Insufficient disk space: {free_mb:.1f}MB available")
                return False
        except Exception:
            pass

        return True

    def process_single_email(self, email: EmailMessage, receiver_client: Optional[IMAPReceiver] = None) -> Optional[Dict[str, Any]]:
        """Processes one email through filtering, job creation, and state updates."""
        logger.info(f"Processing email: Subject='{email.subject}', From='{email.sender.raw}', UID='{email.uid}'")

        if self.state_db.is_message_processed(email.message_id):
            logger.info(f"Skipping already processed message ID: {email.message_id}")
            return None

        self.state_db.record_start(
            message_id=email.message_id,
            uid=email.uid,
            sender=email.sender.raw,
            subject=email.subject
        )

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
            client = receiver_client or self.imap_client
            if self.config.imap.mark_as_read and email.uid:
                client.mark_as_read(email.uid)
            return None

        try:
            job_result = self.job_manager.create_job(email, filter_res)
            logger.info(f"Job Created: {job_result['job_id']} in '{job_result['job_dir']}'")
            
            client = receiver_client or self.imap_client
            if self.config.imap.mark_as_read and email.uid:
                client.mark_as_read(email.uid)

            return job_result
        except Exception as e:
            logger.error(f"Failed to process email into job (Message-ID: {email.message_id}): {e}", exc_info=True)
            self.state_db.record_failure(email.message_id, str(e))
            return None

    def process_once(self) -> int:
        """Performs a single intake pass across all active configured mailboxes."""
        if not self.pre_flight_checks():
            return 0

        jobs_created = 0
        active_mailboxes = self.state_db.get_active_mailboxes()

        if active_mailboxes:
            logger.info(f"Processing {len(active_mailboxes)} active mailbox account(s)...")
            for mb in active_mailboxes:
                try:
                    emails = self.mailbox_manager.fetch_emails_from_mailbox(mb)
                    config = self.mailbox_manager.get_imap_config_for_mailbox(mb)
                    client = IMAPReceiver(config)
                    client.connect()
                    for email_msg in emails:
                        res = self.process_single_email(email_msg, receiver_client=client)
                        if res and res.get("status") == "SUCCESS":
                            jobs_created += 1
                    client.close()
                except Exception as mb_err:
                    logger.error(f"Error processing mailbox '{mb.get('name')}': {mb_err}")
        else:
            # Fallback to default IMAP config
            logger.info("No database mailboxes active. Polling default configured IMAP mailbox...")
            emails = self.imap_client.fetch_unread_emails()
            for email_msg in emails:
                res = self.process_single_email(email_msg)
                if res and res.get("status") == "SUCCESS":
                    jobs_created += 1
            self.imap_client.close()

        self.last_sync_timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        return jobs_created

    # -------------------------------------------------------------------------
    # Thread-Safe Monitoring Daemon Controller (Start / Pause / Resume / Stop)
    # -------------------------------------------------------------------------

    def start_background_monitoring(self):
        """Starts background worker thread if not already running."""
        with self._lock:
            if self._running:
                self._paused = False
                return

            self._running = True
            self._paused = False
            self._worker_thread = threading.Thread(target=self._daemon_loop, daemon=True, name="MailboxPoller")
            self._worker_thread.start()
            logger.info("Background Mailbox Poller thread started.")

    def pause_monitoring(self):
        """Pauses the intake loop without stopping the thread."""
        with self._lock:
            self._paused = True
            logger.info("Mailbox monitoring paused.")

    def resume_monitoring(self):
        """Resumes a paused monitoring loop."""
        with self._lock:
            self._paused = False
            logger.info("Mailbox monitoring resumed.")

    def stop_daemon(self):
        """Gracefully terminates background poller."""
        with self._lock:
            self._running = False
            self._paused = False
        logger.info("Mailbox monitoring stopped.")

    def get_monitoring_status(self) -> Dict[str, Any]:
        """Returns live status of background daemon."""
        with self._lock:
            status_text = "PAUSED" if self._paused else ("RUNNING" if self._running else "STOPPED")
            return {
                "status": status_text,
                "is_running": self._running,
                "is_paused": self._paused,
                "last_sync": self.last_sync_timestamp,
                "active_mailboxes_count": len(self.state_db.get_active_mailboxes()),
                "poll_interval_seconds": self.config.imap.poll_interval_seconds
            }

    def _daemon_loop(self):
        """Continuous background loop for the poller thread."""
        logger.info("Mailbox Poller daemon loop active.")
        while self._running:
            if not self._paused:
                try:
                    self.process_once()
                except Exception as e:
                    logger.error(f"Error in daemon polling cycle: {e}", exc_info=True)

            interval = max(10, self.config.imap.poll_interval_seconds)
            for _ in range(interval):
                if not self._running:
                    break
                time.sleep(1)

    def run_daemon(self):
        """Foreground blocking daemon runner for CLI."""
        if not self.pre_flight_checks():
            return
        self.start_background_monitoring()
        try:
            while self._running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop_daemon()
