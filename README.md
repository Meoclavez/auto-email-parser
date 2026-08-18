# Automatic Email Parser & Downloader (Phase 1)

A self-hosted, on-premises automatic email monitoring, filtering, attachment downloader, and Markdown archiver. Designed for privacy and zero cloud dependencies — all email contents and attachments are processed and stored strictly on the local server.

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
   - Isolated folder hierarchy per enquiry.
5. **Secure File Handling & Quarantine**:
   - Supports documents (PDF, DOCX, XLSX, TXT), images (JPG, PNG, GIF, TIFF), CAD models (DXF, DWG, STEP, IGES), and safe ZIP archives.
   - Path traversal and null-byte injection mitigation.
   - File extension whitelisting and magic byte header signature inspection (blocks disguised executables like `.exe` disguised as `.pdf`).
   - Zip bomb defense with uncompressed size and entry count limits.
   - Quarantining of dangerous attachments without dropping the customer enquiry.
   - Strict file permissions (`0640` for files, `0750` for folders).
6. **Markdown Archiving**:
   - Automatic extraction and conversion of HTML/plaintext email bodies to clean GitHub Flavored Markdown (`email_content.md`).
   - Structured metadata frontmatter/card (From, To, Date, Subject, Message-ID).
   - Attachments table with links, file sizes, and SHA-256 checksums.
   - Warning callouts for quarantined attachments.
7. **Idempotency & State Tracking**:
   - Embedded SQLite database in WAL mode (`email_jobs.db`).
   - Prevents duplicate downloads and duplicate job folders.

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

## Installation & Setup

### 1. Requirements
- Python 3.10+
- Dependencies listed in `requirements.txt`:
  ```bash
  pip install -r requirements.txt
  ```

### 2. Configuration
Copy the template configuration files:
```bash
cp config/config.example.yaml config/config.yaml
cp config/.env.example .env
```

Edit `config/config.yaml` or `.env` with your IMAP credentials and filter rules:
```yaml
imap:
  server: "imap.yourmailserver.com"
  port: 993
  username: "enquiries@yourcompany.com"
  password: "your_secure_password"
  use_ssl: true
  mailbox: "INBOX"
  poll_interval_seconds: 60

filters:
  required_subject_keywords:
    - "RFQ"
    - "Quote"
    - "Enquiry"
    - "Job"
    - "Order"
```

---

## CLI Commands

```bash
# Test IMAP connection and check unread count
python3 main.py test-connection

# Process unread emails in a single pass and exit (ideal for cron)
python3 main.py process-once

# Run continuous background daemon
python3 main.py run

# Check intake metrics and counts
python3 main.py stats

# List recent processed jobs
python3 main.py inspect-jobs --limit 20
```

---

## Running the Demo Simulation

You can test the entire pipeline locally without an external mail server:
```bash
python3 scripts/demo_simulate_intake.py
```

---

## Running Automated Tests

```bash
python3 -m unittest discover -s tests -v
```

---

## Running as a Linux Systemd Service

Create `/etc/systemd/system/email-parser.service`:

```ini
[Unit]
Description=Automatic Email Parser & Downloader Daemon
After=network.target

[Service]
Type=simple
User=appuser
WorkingDirectory=/home/appuser/auto-email-parser
ExecStart=/usr/bin/python3 /home/appuser/auto-email-parser/main.py run --config /home/appuser/auto-email-parser/config/config.yaml
Restart=on-failure
RestartSec=10
EnvironmentFile=/home/appuser/auto-email-parser/.env

[Install]
WantedBy=multi-user.target
```

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now email-parser.service
sudo systemctl status email-parser.service
```
