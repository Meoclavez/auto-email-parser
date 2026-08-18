# Project Map: Automatic Email Parser & Downloader

## 1. Overview
Secure, self-hosted, 100% on-premises email intake, filtering, job directory provisioning, attachment downloader, and markdown archiver. Built for privacy with zero cloud dependencies.

## 2. Directory & Component Architecture

```
auto-email-parser/
├── config/
│   ├── config.yaml                     # Active runtime YAML configuration
│   ├── config.example.yaml             # Documented template config
│   └── .env.example                    # Environment variable secrets template
├── src/
│   ├── config.py                       # Configuration models (IMAP, Filters, Storage, Security)
│   ├── email_receiver/
│   │   ├── models.py                   # Data models (EmailMessage, AttachmentInfo, FilterResult, JobManifest)
│   │   ├── filters.py                  # EmailFilter rule engine (domains, keywords, regex, intake addresses)
│   │   └── imap_client.py              # IMAPReceiver with SSL/TLS, auto-reconnect, exponential backoff, MIME decoder
│   ├── security/
│   │   ├── sanitizer.py                # Filename sanitizer (path traversal defense, special char stripping, slug generator)
│   │   └── validator.py                # AttachmentValidator (magic byte signatures, extension whitelisting, zip bomb check)
│   ├── file_handler/
│   │   ├── attachment_manager.py       # AttachmentManager (consistent naming, atomic save, quarantine handler, chmod 0640)
│   │   └── markdown_writer.py          # EmailMarkdownWriter (HTML to GFM converter, metadata card, warning annotations)
│   ├── storage/
│   │   ├── state_db.py                 # StateDatabase (SQLite WAL database for idempotency, retry tracking, atomic job ID counter)
│   │   └── job_manager.py              # JobManager (orchestrates folder layout, manifest.json, email_content.md, attachments)
│   └── service.py                      # EmailParserService (daemon loop, pre-flight checks, graceful signal handling)
├── storage/
│   ├── jobs/                           # Target directory for generated enquiry folders
│   ├── quarantine/                     # Isolated folder for quarantined suspicious attachments
│   └── email_jobs.db                   # SQLite state tracking database
├── tests/
│   ├── test_sanitizer.py               # Path traversal, null byte, reserved device, and slug tests
│   ├── test_validator.py               # Magic bytes, extension checking, zip bomb, disguised EXE tests
│   ├── test_filters.py                 # Whitelist/blacklist domain, keyword, and address rule tests
│   ├── test_markdown_writer.py         # HTML to Markdown and attachment table formatting tests
│   ├── test_job_manager.py             # Job ID sequencing, folder creation, and manifest tests
│   └── test_service_pipeline.py        # Complete end-to-end integration pipeline tests
├── scripts/
│   └── demo_simulate_intake.py         # Mock simulation test harness
├── main.py                             # CLI entrypoint (run, process-once, test-connection, stats, inspect-jobs)
├── requirements.txt                    # Project dependencies
└── README.md                           # Complete deployment, configuration, and security documentation
```

## 3. Key Module APIs & Logic

### `src.security.sanitizer`
* `sanitize_filename(raw_name, max_length=150, fallback="attachment") -> str`: Strips path components, null bytes, dangerous shell chars, reserved Windows/DOS names (`CON`, `NUL`, etc.), enforces max length.
* `sanitize_identifier(name, max_length=50, fallback="client") -> str`: Produces clean alphanumeric slugs for folders.
* `extract_client_identifier(sender, subject) -> str`: Derives company name from non-public email domains or sender names.
* `extract_job_reference(subject, patterns) -> Optional[str]`: Extracts RFQ/PO/Job reference numbers from subject lines.

### `src.security.validator`
* `AttachmentValidator.validate(filename, data) -> ValidationResult`:
  * Validates size limits (`max_file_size_mb`).
  * Checks against forbidden extensions (`.exe`, `.bat`, `.sh`, `.vbs`, etc.).
  * Verifies file magic signatures (PDF `%PDF-`, PNG, JPEG, CAD DXF/DWG/STEP/IGES, ZIP).
  * Detects disguised executables (e.g. Windows `MZ` or Linux `ELF` headers disguised with a `.pdf` extension).
  * Safely inspects ZIP archives for zip bombs (uncompressed ratio, file count) and internal path traversal.

### `src.email_receiver.filters`
* `EmailFilter.evaluate(email: EmailMessage) -> FilterResult`:
  * Whitelist and blacklist domain filters.
  * Required subject keywords (ANY or ALL matching) + custom regex.
  * Excluded subject keywords (auto-replies, out-of-office).
  * Dedicated intake address matching (To/Cc).
  * Attachment presence requirement.

### `src.email_receiver.imap_client`
* `IMAPReceiver.connect() -> bool`: Connects with SSL/TLS or STARTTLS with exponential retry backoff.
* `IMAPReceiver.fetch_unread_emails() -> List[EmailMessage]`: Fetches UNSEEN emails in batches.
* `IMAPReceiver.parse_raw_email(raw_bytes, uid) -> EmailMessage`: RFC 822 / MIME parser with multi-codec charset fallback (`utf-8`, `latin-1`, `windows-1252`, `replace`).
* `IMAPReceiver.mark_as_read(uid)`: Marks email as `\Seen`.

### `src.storage.state_db`
* `StateDatabase.get_next_job_id(prefix="JOB", date_obj=None) -> str`: Generates sequential IDs (`JOB-YYYYMMDD-XXXX`).
* `StateDatabase.is_message_processed(message_id) -> bool`: Idempotency guard.
* `StateDatabase.record_start()`, `record_success()`, `record_ignored()`, `record_failure()`: Transactional state updates.
* `StateDatabase.get_stats()`, `get_recent_jobs()`: Monitoring queries.

### `src.storage.job_manager`
* `JobManager.create_job(email, filter_result) -> Dict`:
  * Provisions folder: `storage/jobs/{job_id}_{client_slug}/`.
  * Saves attachments into `attachments/{job_id}_{idx:02d}_{sanitized_name}` with `0640` permissions.
  * Quarantines rejected attachments into `storage/quarantine/{job_id}_{idx:02d}_{name}.quarantine`.
  * Generates `email_content.md` and `manifest.json`.
  * Updates SQLite database.

### `src.file_handler.markdown_writer`
* `EmailMarkdownWriter.generate_markdown(email, job_id, filter_result, saved_attachments, quarantined_attachments) -> str`: Converts email metadata, security alert boxes, attachment tables, and HTML/plaintext bodies into sanitized GFM.
* `EmailMarkdownWriter.html_to_markdown(html) -> str`: Converts HTML tags into Markdown while stripping `<script>`, `<style>`, and `<iframe>`.

### `src.service`
* `EmailParserService.run_daemon()`: Continuous monitoring loop with configurable poll interval and graceful `SIGINT`/`SIGTERM` handling.
* `EmailParserService.process_once() -> int`: Single batch intake run.
* `EmailParserService.pre_flight_checks() -> bool`: Disk space, permissions, and database verification.

## 4. CLI Usage
* `python3 main.py run`: Starts the continuous background daemon.
* `python3 main.py process-once`: Executes a single polling and processing pass.
* `python3 main.py test-connection`: Verifies IMAP credentials, latency, and unread counts.
* `python3 main.py stats`: Displays processing metrics (total, processed, ignored, failed).
* `python3 main.py inspect-jobs --limit 20`: Lists recent job records.
