# Automatic Email Parser, Downloader & Secure Web Dashboard

A self-hosted, 100% on-premises automatic email monitoring, filtering, attachment downloader, Markdown archiver, and secure Web Dashboard. Designed for air-gapped or on-premises servers with zero external cloud dependencies.

---

## Key Features

1. **100% Local & Privacy First**: No external APIs, no third-party cloud data transmission, and zero telemetry.
2. **Email Monitoring & Polling**:
   - Secure IMAP over TLS/SSL (Port 993) or STARTTLS.
   - Exponential backoff retry on network drops, timeouts, and server disconnects.
   - Configurable polling intervals or IMAP IDLE push.
3. **Multi-Criteria Filter Engine**:
   - Sender domain whitelist and blacklist filtering.
   - Subject keyword detection (literal and regex match).
   - Dedicated intake address filtering (`To` / `Cc`).
   - Exclusion of out-of-office and automated bounce-backs.
4. **Enquiry & Job Management**:
   - Automatic sequential Job ID generation (`JOB-YYYYMMDD-XXXX`).
   - Clean client identifier slug extraction (e.g. `JOB-20260819-0001_acme-aerospace_4089`).
   - Isolated folder hierarchy per enquiry with `email_content.md` and `manifest.json`.
5. **Hardened Security & Quarantine**:
   - Supports documents (PDF, DOCX, XLSX, TXT), images (JPG, PNG, GIF, TIFF), CAD models (DXF, DWG, STEP, IGES), and safe ZIP archives.
   - Path traversal and null-byte injection mitigation.
   - File extension whitelisting and magic byte header signature inspection (blocks disguised executables like `.exe` disguised as `.pdf`).
   - Zip bomb defense with uncompressed size and entry count limits.
   - Quarantining of dangerous attachments without dropping the customer enquiry.
   - Strict file permissions (`0640` for files, `0750` for folders).
6. **Secure Web Dashboard (On-Premises)**:
   - **Modern Dark/Glassmorphic SPA**: 100% self-contained HTML/CSS/JS with zero external CDN dependencies.
   - **Local Authentication**: Argon2id password hashing, session tokens, and IP brute-force rate-limiting.
   - **Enquiry Explorer**: Real-time search, status filtering, and rendered Markdown viewer.
   - **Safe File Serving**: Enforces `Content-Disposition: attachment`, `X-Content-Type-Options: nosniff`, and strict `Content-Security-Policy`.
   - **Quarantine Center**: Review and purge flagged security threats.
   - **Live Updates**: Server-Sent Events (SSE) stream for real-time dashboard notifications.

---

## Directory Structure

```
storage/
└── jobs/
    └── JOB-20260819-0001_acme-aerospace_4089/
        ├── email_content.md       # Metadata, attachments table, and parsed body
        ├── manifest.json          # Audit log with SHA-256 hashes and timestamps
        └── attachments/
            ├── JOB-20260819-0001_01_bracket_spec_revB.pdf
            └── JOB-20260819-0001_02_bracket_profile.dxf
```

---

## Installation & Quickstart

### 1. Requirements
- Python 3.10+
- Dependencies in `requirements.txt` (`pip install -r requirements.txt`)

### 2. Configuration
Copy the template configuration files:
```bash
cp config/config.example.yaml config/config.yaml
cp config/.env.example .env
```

---

## CLI Commands

### 1. Web Dashboard
```bash
# Start the web dashboard (default: http://127.0.0.1:8080)
# Default login: admin / AdminPass123!
python3 main.py web --port 8080

# Create a new user account
python3 main.py create-user --username john_doe --password MySecretPassword123! --role estimator
```

### 2. Email Intake & Diagnostics
```bash
# Test IMAP connection and check unread count
python3 main.py test-connection

# Process unread emails in a single pass (cron mode)
python3 main.py process-once

# Run continuous background email monitoring daemon
python3 main.py run

# Check intake metrics and counts
python3 main.py stats

# List recent processed jobs
python3 main.py inspect-jobs --limit 20
```

---

## Automated Tests

Run the full 44 unit and integration test suite:
```bash
python3 -m unittest discover -s tests -v
```

---

## Production Nginx & Systemd Deployment

### 1. Nginx Reverse Proxy
Copy [`deploy/nginx.conf`](file:///home/meoclavezz/Projects-1/auto-email-parser/deploy/nginx.conf) to `/etc/nginx/sites-available/email-parser.conf`, update your domain/certificates, and reload Nginx:
```bash
sudo ln -s /etc/nginx/sites-available/email-parser.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### 2. Systemd Web Service
Copy [`deploy/email-parser-web.service`](file:///home/meoclavezz/Projects-1/auto-email-parser/deploy/email-parser-web.service) to `/etc/systemd/system/email-parser-web.service`:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now email-parser-web.service
sudo systemctl status email-parser-web.service
```
