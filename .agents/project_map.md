# Project Map: Automatic Email Parser, Downloader & Secure Web Dashboard

## 1. Overview
Secure, self-hosted, 100% on-premises automatic email monitoring, filtering, job directory provisioning, attachment downloader, Markdown archiver, and secure Web Dashboard. Designed for air-gapped/on-prem environments with zero cloud dependencies.

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
│   │   ├── state_db.py                 # StateDatabase (SQLite WAL database for idempotency, retry tracking, user auth, sessions)
│   │   └── job_manager.py              # JobManager (orchestrates folder layout, manifest.json, email_content.md, attachments)
│   ├── web/
│   │   ├── app.py                      # Flask Application Factory with security headers & session middleware
│   │   ├── auth.py                     # Argon2id password hashing, session tokens, login rate limiter, and RBAC
│   │   ├── routes/
│   │   │   ├── auth_routes.py          # /api/auth/login, /api/auth/logout, /api/auth/me, /login
│   │   │   ├── job_routes.py           # /api/jobs, /api/jobs/<job_id>, /api/jobs/<job_id>/markdown, /api/jobs/<job_id>/attachments/<file>
│   │   │   ├── quarantine_routes.py    # /api/quarantine, /api/quarantine/<file>/download
│   │   │   ├── config_routes.py        # /api/config, /api/config/filters (Admin only)
│   │   │   ├── service_routes.py       # /api/service/status, /api/service/sync-now, /api/service/test-imap
│   │   │   └── events_routes.py        # /api/events/stream (SSE live stream)
│   │   └── static/
│   │       ├── css/dashboard.css       # Modern Dark/Glassmorphic self-contained CSS
│   │       ├── js/api.js               # Authenticated API client
│   │       ├── js/app.js               # Single Page Dashboard application controller
│   │       ├── login.html              # Secure Login portal
│   │       └── index.html              # Main Single Page Application
│   └── service.py                      # EmailParserService (daemon loop, pre-flight checks, graceful signal handling)
├── deploy/
│   ├── nginx.conf                      # Production hardened reverse proxy with TLS, HSTS, and CSP
│   └── email-parser-web.service        # Systemd unit file for web dashboard
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
│   ├── test_service_pipeline.py        # Complete end-to-end integration pipeline tests
│   ├── test_web_auth.py                # Argon2 password hashing, session tokens, and rate-limiting tests
│   └── test_web_api.py                 # Web API endpoints, safe attachment download, and security headers tests
├── scripts/
│   └── demo_simulate_intake.py         # Mock simulation test harness
├── main.py                             # CLI entrypoint (run, process-once, test-connection, stats, inspect-jobs, web, create-user)
├── requirements.txt                    # Project dependencies
└── README.md                           # Complete deployment, configuration, and security documentation
```

## 3. Key Web APIs & Security Layer

### `src.web.auth`
* `PasswordManager.hash_password(password)`: Hashes using Argon2id (`time_cost=3, memory_cost=64MB, parallelism=4`).
* `PasswordManager.verify_password(password, hash)`: Constant-time password verification.
* `AuthService.authenticate_user(username, password, ip)`: Rate-limited login verification (blocks IP after 5 failed attempts for 15 minutes).
* `@login_required`: Protects routes ensuring valid session cookie (`HttpOnly; Secure; SameSite=Strict`).
* `@admin_required`: Restricts sensitive endpoints (config editing, quarantine management) to admin role.

### `src.web.routes`
* `GET /api/jobs`: List and search enquiries with pagination.
* `GET /api/jobs/<job_id>`: Retrieves job record & `manifest.json`.
* `GET /api/jobs/<job_id>/markdown`: Retrieves parsed `email_content.md`.
* `GET /api/jobs/<job_id>/attachments/<filename>`: Safely streams attachments with `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`, `Content-Security-Policy: default-src 'none'`, and path traversal validation.
* `POST /api/service/sync-now`: Triggers on-demand intake cycle.
* `GET /api/events/stream`: Live Server-Sent Events (SSE) stream.

## 4. CLI Usage
* `python3 main.py web --port 8080`: Starts the web dashboard server.
* `python3 main.py create-user -u <user> -p <pass> --role admin`: Provisions user account.
* `python3 main.py run`: Starts the continuous background IMAP listener.
* `python3 main.py process-once`: Executes a single polling and processing pass.
* `python3 main.py stats`: Displays processing metrics.
