# Project Map: Enterprise Automatic Email Parser, Downloader & Web Dashboard

## 1. Overview
Secure, self-hosted, 100% on-premises automatic email monitoring, multi-mailbox encrypted management, attachment downloader, Markdown archiver, live daemon controller, and professional light-themed Web Dashboard.

## 2. Directory & Component Architecture

```
auto-email-parser/
├── config/
│   ├── config.yaml                     # Active runtime YAML configuration
│   ├── config.example.yaml             # Documented template config
│   ├── master.key                      # Auto-generated AES master key (0600)
│   └── .env.example                    # Environment variable secrets template
├── src/
│   ├── config.py                       # Configuration models (IMAP, Filters, Storage, Security)
│   ├── email_receiver/
│   │   ├── models.py                   # Data models (EmailMessage, AttachmentInfo, FilterResult, JobManifest)
│   │   ├── filters.py                  # EmailFilter rule engine (domains, keywords, regex, intake addresses)
│   │   ├── imap_client.py              # IMAPReceiver with SSL/TLS, auto-reconnect, exponential backoff, MIME decoder
│   │   └── mailbox_manager.py          # MailboxManager (multi-mailbox coordinator, encrypted credential decryption)
│   ├── security/
│   │   ├── sanitizer.py                # Filename sanitizer (path traversal defense, special char stripping, slug generator)
│   │   ├── validator.py                # AttachmentValidator (magic byte signatures, extension whitelisting, zip bomb check)
│   │   └── encryption.py               # CredentialCipher (AES-128/Fernet authenticated encryption at rest)
│   ├── file_handler/
│   │   ├── attachment_manager.py       # AttachmentManager (consistent naming, atomic save, quarantine handler, chmod 0640)
│   │   └── markdown_writer.py          # EmailMarkdownWriter (HTML to GFM converter, metadata card, warning annotations)
│   ├── storage/
│   │   ├── state_db.py                 # StateDatabase (SQLite WAL database for jobs, mailboxes, users, companies, notes, audit logs)
│   │   └── job_manager.py              # JobManager (orchestrates folder layout, manifest.json, email_content.md, attachments)
│   ├── web/
│   │   ├── app.py                      # Flask Application Factory with security headers & session middleware
│   │   ├── auth.py                     # Argon2id password hashing, session tokens, login rate limiter, and RBAC
│   │   ├── routes/
│   │   │   ├── auth_routes.py          # /api/auth/login, /api/auth/logout, /api/auth/me, /login
│   │   │   ├── job_routes.py           # /api/jobs, /api/jobs/<job_id>, /api/jobs/<job_id>/status, /api/jobs/<job_id>/notes, /api/jobs/upload
│   │   │   ├── mailbox_routes.py       # /api/mailboxes (CRUD, test connection, active toggle)
│   │   │   ├── monitoring_routes.py    # /api/monitoring (status, start, pause, resume, sync)
│   │   │   ├── user_routes.py          # /api/users, /api/auth/register (team management & company registration)
│   │   │   ├── quarantine_routes.py    # /api/quarantine, /api/quarantine/<file>/download
│   │   │   ├── config_routes.py        # /api/config, /api/config/filters (Admin only)
│   │   │   ├── service_routes.py       # /api/service/status, /api/service/sync-now, /api/service/test-imap
│   │   │   └── events_routes.py        # /api/events/stream (SSE live stream)
│   │   └── static/
│   │       ├── css/dashboard.css       # Modern Professional Light/White Theme CSS
│   │       ├── js/icons.js             # High-resolution vector SVG icon library (Zero emojis)
│   │       ├── js/api.js               # Authenticated API client
│   │       ├── js/app.js               # Single Page Dashboard application controller
│   │       ├── login.html              # Professional Login portal
│   │       ├── register.html           # Company & user registration portal
│   │       └── index.html              # Main Single Page Application
│   └── service.py                      # EmailParserService & MonitoringController (dynamic background thread pool)
├── deploy/
│   ├── nginx.conf                      # Production hardened reverse proxy with TLS, HSTS, and CSP
│   └── email-parser-web.service        # Systemd unit file for web dashboard
├── storage/
│   ├── jobs/                           # Target directory for generated enquiry folders
│   ├── quarantine/                     # Isolated folder for quarantined suspicious attachments
│   └── email_jobs.db                   # SQLite state tracking database
├── tests/
│   ├── test_encryption.py              # CredentialCipher AES encryption tests
│   ├── test_mailbox_manager.py         # Multi-mailbox storage and connection tests
│   ├── test_job_notes_and_users.py     # Estimator notes, status pipeline, and user registration tests
│   ├── test_sanitizer.py               # Path traversal, null byte, reserved device, and slug tests
│   ├── test_validator.py               # Magic bytes, extension checking, zip bomb, disguised EXE tests
│   ├── test_filters.py                 # Whitelist/blacklist domain, keyword, and address rule tests
│   ├── test_markdown_writer.py         # HTML to Markdown and attachment table formatting tests
│   ├── test_job_manager.py             # Job ID sequencing, folder creation, and manifest tests
│   ├── test_service_pipeline.py        # Complete end-to-end integration pipeline tests
│   ├── test_web_auth.py                # Argon2 password hashing, session tokens, and rate-limiting tests
│   └── test_web_api.py                 # Web API endpoints, safe attachment download, and security headers tests
├── scripts/
│   └── demo_simulate_intake.py         # Mock simulation test harness
├── main.py                             # CLI entrypoint (run, process-once, test-connection, stats, inspect-jobs, web, create-user)
├── requirements.txt                    # Project dependencies
└── README.md                           # Complete deployment, configuration, and security documentation
```

## 3. Key Services & APIs

* **Multi-Mailbox Store**: Encrypted credentials (`AES-256`/`Fernet`), per-mailbox Active toggle, and instant connection diagnostic.
* **Live Daemon Controller**: Thread-safe background monitoring coordinator (`start`, `pause`, `resume`, `sync`).
* **Company & Staff Registration**: Self-service company registration (`/register`) and role administration.
* **Estimator Workflow**: Job status pipeline (`NEW` -> `IN_REVIEW` -> `QUOTED` -> `ARCHIVED`) and internal notes.
* **Vector SVG UI**: Modern light theme (`#ffffff` / `#f8fafc`) with clean line SVGs (no emoji stickers).
