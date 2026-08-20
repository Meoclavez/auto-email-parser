# Enterprise Automatic Email Parser, Downloader & Management Suite

A self-hosted, 100% on-premises automatic email monitoring, multi-mailbox encrypted management, attachment downloader, Markdown archiver, live daemon controller, and professional light-themed Web Dashboard.

---

## 🌟 Key Features & Services

1. **Multi-Mailbox Management & Credential Encryption**:
   - Add, edit, and monitor multiple dedicated IMAP email accounts concurrently (e.g. `rfq@company.com`, `sales@company.com`).
   - Passwords encrypted at rest using **AES-128/Fernet** authenticated symmetric encryption with master key protection (`config/master.key`).
   - One-click **"Test Connection"** diagnostic with instantaneous latency, SSL handshake, and unread count checks.
   - Individual Active/Inactive toggles per mailbox account.

2. **Live Monitoring Daemon Controller**:
   - Dynamic **Start / Pause / Resume / Immediate Sync** controls directly from the web dashboard.
   - Live health indicators (Running, Paused, Syncing, Idle) and next poll countdown.

3. **Secure Company & User Registration / Team RBAC**:
   - Company onboarding and staff registration portal (`/register`).
   - Role-Based Access Control (**Admin**, **Estimator**, **Viewer**) with account deactivation and role assignment.
   - State-of-the-art **Argon2id** password hashing and IP brute-force rate-limiting.

4. **Estimator Pipeline Workflow & Notes**:
   - Track enquiries through a structured pipeline: `NEW` → `IN_REVIEW` → `QUOTED` → `ARCHIVED`.
   - Attach internal estimation notes and pricing remarks to each enquiry.
   - Manual `.eml` email or drawing archive drag-and-drop upload.

5. **Hardened Attachment Handling & Quarantine**:
   - Detects and downloads documents (PDF, DOCX, XLSX, TXT), images (JPG, PNG, GIF, TIFF), CAD models (DXF, DWG, STEP, IGES), and safe ZIP archives.
   - Strict filename sanitization and path traversal defense.
   - Magic byte header inspection (blocks disguised `.exe` / `.elf` binaries).
   - Safe zip bomb limits and non-destructive quarantine isolation (`storage/quarantine/`).

6. **Professional Light/White Enterprise UI**:
   - Crisp white/slate aesthetic (`#ffffff` / `#f8fafc`) with subtle borders and clean typography.
   - High-resolution **vector SVG icons** throughout (Inbox, Mail, Shield, Check, Clock, Server, Play, Pause, Key, Users, Settings) — **strictly zero emojis**.

---

## 🚀 Quickstart & Usage

### 1. Installation
```bash
pip install -r requirements.txt
```

### 2. Start the Web Dashboard
```bash
# Start the dashboard (Default: http://127.0.0.1:8080)
# Default login: admin / AdminPass123!
python3 main.py web --port 8080
```

### 3. Create Additional Users
```bash
python3 main.py create-user --username estimator_1 --password MySecretPass123! --role estimator
```

### 4. Run Automated Test Suite
```bash
python3 -m unittest discover -s tests -v
# 51 tests (OK)
```

---

## 🔒 Production Deployment

- Hardened **Nginx Reverse Proxy** template with TLS 1.3, HSTS, and CSP: [`deploy/nginx.conf`](file:///home/meoclavezz/Projects-1/auto-email-parser/deploy/nginx.conf)
- **Systemd Web Service** unit file: [`deploy/email-parser-web.service`](file:///home/meoclavezz/Projects-1/auto-email-parser/deploy/email-parser-web.service)
