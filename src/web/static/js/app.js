/**
 * Enterprise Email Parser & Downloader - Modern Dashboard SPA Controller
 * Powered by pure JavaScript and Vector SVGs (Zero Emojis).
 */

document.addEventListener("DOMContentLoaded", () => {
  App.init();
});

const App = {
  currentUser: null,
  currentJobId: null,
  activeTab: "jobs",
  searchTerm: "",
  statusFilter: "ALL",

  async init() {
    this.renderStaticIcons();
    await this.checkAuth();
    this.setupEventListeners();
    await this.loadStats();
    await this.loadJobs();
    this.initEventStream();
  },

  renderStaticIcons() {
    document.getElementById("brand-logo-slot").innerHTML = Icons.brandMonogram(32);
    document.getElementById("icon-sync-slot").innerHTML = Icons.refresh(16);
    document.getElementById("icon-search-slot").innerHTML = Icons.search(16);
    document.getElementById("icon-logout-slot").innerHTML = Icons.logOut(16);

    // KPI icons
    document.getElementById("kpi-icon-total").innerHTML = Icons.mail(22);
    document.getElementById("kpi-icon-processed").innerHTML = Icons.checkCircle(22);
    document.getElementById("kpi-icon-quarantined").innerHTML = Icons.shieldAlert(22);
    document.getElementById("kpi-icon-storage").innerHTML = Icons.server(22);

    // Tab icons
    document.getElementById("tab-icon-jobs").innerHTML = Icons.inbox(16);
    document.getElementById("tab-icon-mailboxes").innerHTML = Icons.mail(16);
    document.getElementById("tab-icon-monitoring").innerHTML = Icons.play(16);
    document.getElementById("tab-icon-config").innerHTML = Icons.filter(16);
    document.getElementById("tab-icon-quarantine").innerHTML = Icons.shield(16);
    document.getElementById("tab-icon-team").innerHTML = Icons.users(16);
  },

  async checkAuth() {
    try {
      const res = await API.get("/api/auth/me");
      if (res && res.authenticated) {
        this.currentUser = res.user;
        document.getElementById("user-name").textContent = this.currentUser.username;
        document.getElementById("user-role-badge").textContent = this.currentUser.role.toUpperCase();

        // Admin-only tabs
        if (this.currentUser.role !== "admin") {
          document.querySelectorAll(".admin-only").forEach(el => el.style.display = "none");
        }
      }
    } catch (e) {
      window.location.href = "/login";
    }
  },

  setupEventListeners() {
    // Navigation Tabs
    document.querySelectorAll(".tab-btn").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const targetTab = btn.dataset.tab;
        this.switchTab(targetTab);
      });
    });

    // Search input debouncing
    let debounceTimer;
    document.getElementById("search-input").addEventListener("input", (e) => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        this.searchTerm = e.target.value;
        this.loadJobs();
      }, 300);
    });

    // Status filter
    document.getElementById("status-filter").addEventListener("change", (e) => {
      this.statusFilter = e.target.value;
      this.loadJobs();
    });

    // Sync button
    document.getElementById("sync-now-btn").addEventListener("click", () => {
      this.triggerSync();
    });

    // Logout button
    document.getElementById("logout-btn").addEventListener("click", () => {
      this.logout();
    });

    // Modal Close
    document.getElementById("modal-close").addEventListener("click", () => {
      this.closeModal();
    });

    // Add Mailbox Modal
    document.getElementById("btn-add-mailbox").addEventListener("click", () => {
      this.openAddMailboxModal();
    });

    document.getElementById("mailbox-modal-close").addEventListener("click", () => {
      document.getElementById("mailbox-modal").classList.remove("active");
    });

    document.getElementById("form-add-mailbox").addEventListener("submit", (e) => {
      e.preventDefault();
      this.saveNewMailbox();
    });

    // Add Team User Modal
    const btnAddUser = document.getElementById("btn-add-user");
    if (btnAddUser) {
      btnAddUser.addEventListener("click", () => {
        document.getElementById("user-modal").classList.add("active");
      });
    }

    document.getElementById("user-modal-close").addEventListener("click", () => {
      document.getElementById("user-modal").classList.remove("active");
    });

    document.getElementById("form-add-user").addEventListener("submit", (e) => {
      e.preventDefault();
      this.saveNewUser();
    });

    // Save filters config button
    const saveFiltersBtn = document.getElementById("save-filters-btn");
    if (saveFiltersBtn) {
      saveFiltersBtn.addEventListener("click", () => this.saveFilterConfig());
    }

    // Monitoring controls
    document.getElementById("btn-start-monitor").addEventListener("click", () => this.controlMonitoring("start"));
    document.getElementById("btn-pause-monitor").addEventListener("click", () => this.controlMonitoring("pause"));
    document.getElementById("btn-resume-monitor").addEventListener("click", () => this.controlMonitoring("resume"));
  },

  switchTab(tabName) {
    this.activeTab = tabName;
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
    document.querySelector(`.tab-btn[data-tab="${tabName}"]`).classList.add("active");

    const tabViews = ["jobs", "mailboxes", "monitoring", "config", "quarantine", "team"];
    tabViews.forEach(v => {
      const el = document.getElementById(`tab-${v}-view`);
      if (el) el.style.display = (v === tabName) ? "block" : "none";
    });

    if (tabName === "mailboxes") this.loadMailboxes();
    if (tabName === "monitoring") this.loadMonitoringStatus();
    if (tabName === "quarantine") this.loadQuarantine();
    if (tabName === "config") this.loadConfig();
    if (tabName === "team") this.loadTeamUsers();
  },

  async loadStats() {
    try {
      const stats = await API.get("/api/stats");
      if (!stats) return;

      document.getElementById("stat-total").textContent = stats.TOTAL || 0;
      document.getElementById("stat-processed").textContent = stats.PROCESSED || 0;
      document.getElementById("stat-quarantined").textContent = stats.QUARANTINED || 0;
      document.getElementById("stat-disk").textContent = `${stats.DISK_FREE_MB || 0} MB`;
    } catch (err) {
      console.error("Failed to load stats", err);
    }
  },

  async loadJobs() {
    const tableBody = document.getElementById("jobs-table-body");
    tableBody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:var(--text-muted); padding:2rem;">Loading enquiries...</td></tr>`;

    try {
      let url = `/api/jobs?limit=50&offset=0`;
      if (this.searchTerm) url += `&search=${encodeURIComponent(this.searchTerm)}`;
      if (this.statusFilter !== "ALL") url += `&status=${encodeURIComponent(this.statusFilter)}`;

      const data = await API.get(url);
      if (!data || !data.jobs || data.jobs.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:var(--text-muted); padding:2rem;">No matching enquiries found.</td></tr>`;
        return;
      }

      tableBody.innerHTML = data.jobs.map(j => {
        let badgeClass = "badge-muted";
        if (j.status === "PROCESSED" || j.status === "QUOTED") badgeClass = "badge-success";
        else if (j.status === "FAILED" || j.status === "REJECTED") badgeClass = "badge-danger";
        else if (j.status === "PENDING" || j.status === "IN_REVIEW") badgeClass = "badge-warning";

        const timeStr = j.updated_at ? new Date(j.updated_at).toLocaleString() : "-";

        return `
          <tr class="clickable-row" onclick="App.openJobDetail('${j.job_id || j.message_id}')">
            <td><strong style="color:var(--primary);">${this.escapeHtml(j.job_id || "PENDING")}</strong></td>
            <td>${this.escapeHtml(j.sender || "Unknown")}</td>
            <td>${this.escapeHtml(j.subject || "(No Subject)")}</td>
            <td><span class="badge ${badgeClass}">${j.status}</span></td>
            <td style="color:var(--text-muted); font-size:0.8rem;">${timeStr}</td>
          </tr>
        `;
      }).join("");

    } catch (err) {
      tableBody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:var(--danger);">Failed to load jobs.</td></tr>`;
    }
  },

  async openJobDetail(jobId) {
    this.currentJobId = jobId;
    const modal = document.getElementById("job-modal");
    modal.classList.add("active");
    document.getElementById("modal-job-title").textContent = `Enquiry: ${jobId}`;

    const bodyContainer = document.getElementById("modal-job-body");
    bodyContainer.innerHTML = `<div style="text-align:center; padding:2rem;">Loading enquiry details...</div>`;

    try {
      const [jobData, mdData] = await Promise.all([
        API.get(`/api/jobs/${encodeURIComponent(jobId)}`),
        API.get(`/api/jobs/${encodeURIComponent(jobId)}/markdown`).catch(() => null)
      ]);

      const manifest = jobData.manifest;
      const job = jobData.job;
      let html = "";

      // Pipeline Status & Actions Bar
      html += `
        <div style="display:flex; justify-content:space-between; align-items:center; background:#f8fafc; border:1px solid var(--border-color); border-radius:var(--radius-sm); padding:0.75rem 1rem; margin-bottom:1.25rem;">
          <div style="display:flex; align-items:center; gap:0.75rem;">
            <span style="font-weight:600; font-size:0.85rem;">Status:</span>
            <select class="filter-select" onchange="App.changeJobStatus('${jobId}', this.value)" style="padding:0.35rem 0.65rem;">
              <option value="PROCESSED" ${job.status === 'PROCESSED' ? 'selected' : ''}>PROCESSED</option>
              <option value="IN_REVIEW" ${job.status === 'IN_REVIEW' ? 'selected' : ''}>IN_REVIEW</option>
              <option value="QUOTED" ${job.status === 'QUOTED' ? 'selected' : ''}>QUOTED</option>
              <option value="ARCHIVED" ${job.status === 'ARCHIVED' ? 'selected' : ''}>ARCHIVED</option>
              <option value="REJECTED" ${job.status === 'REJECTED' ? 'selected' : ''}>REJECTED</option>
            </select>
          </div>
          <span style="font-size:0.8rem; color:var(--text-muted);">From: ${this.escapeHtml(job.sender)}</span>
        </div>
      `;

      // Attachments Section
      if (manifest && manifest.attachments && manifest.attachments.length > 0) {
        html += `<h4 style="margin-bottom:0.65rem; color:var(--text-main);">Downloadable Drawings & Attachments</h4><div style="margin-bottom:1.25rem;">`;
        manifest.attachments.forEach(att => {
          const downloadUrl = `/api/jobs/${encodeURIComponent(jobId)}/attachments/${encodeURIComponent(att.filename)}`;
          const sizeKb = (att.size_bytes / 1024).toFixed(1);
          html += `
            <div class="attachment-card">
              <div class="attachment-meta">
                <span style="color:var(--primary);">${Icons.fileText(20)}</span>
                <div>
                  <div style="font-weight:600; color:var(--text-main); font-size:0.875rem;">${this.escapeHtml(att.filename)}</div>
                  <div style="font-size:0.75rem; color:var(--text-muted);">${sizeKb} KB • SHA-256: ${att.sha256 ? att.sha256.substring(0, 10) + '...' : 'N/A'}</div>
                </div>
              </div>
              <a href="${downloadUrl}" class="btn btn-primary btn-sm" download>Download</a>
            </div>
          `;
        });
        html += `</div>`;
      }

      // Quarantined security warnings
      if (manifest && manifest.quarantined_attachments && manifest.quarantined_attachments.length > 0) {
        html += `<div style="background:var(--danger-subtle); border:1px solid var(--danger-border); border-radius:var(--radius-sm); padding:1rem; margin-bottom:1.25rem;">
          <strong style="color:var(--danger); display:flex; align-items:center; gap:0.4rem;">${Icons.shieldAlert(18)} Quarantined Threats Isolated:</strong>
          <ul style="margin-left:1.5rem; margin-top:0.4rem; font-size:0.85rem; color:var(--text-main);">`;
        manifest.quarantined_attachments.forEach(qa => {
          html += `<li><strong>${this.escapeHtml(qa.original_name)}</strong>: ${this.escapeHtml(qa.reason)}</li>`;
        });
        html += `</ul></div>`;
      }

      // Rendered Markdown
      if (mdData && mdData.content) {
        html += `<h4 style="margin-bottom:0.65rem; color:var(--text-main);">Email Markdown Content</h4>`;
        html += `<div class="markdown-view">${this.renderSanitizedMarkdown(mdData.content)}</div>`;
      }

      // Internal Notes Section
      html += `
        <div style="margin-top:1.5rem; border-top:1px solid var(--border-color); padding-top:1.25rem;">
          <h4 style="margin-bottom:0.65rem; color:var(--text-main);">Internal Estimation Notes</h4>
          <div id="job-notes-list" style="margin-bottom:1rem;">
            ${(jobData.notes || []).map(n => `
              <div style="background:#f8fafc; border:1px solid var(--border-color); border-radius:var(--radius-sm); padding:0.65rem 0.85rem; margin-bottom:0.5rem;">
                <div style="display:flex; justify-content:space-between; font-size:0.75rem; color:var(--text-muted); margin-bottom:0.25rem;">
                  <strong>${this.escapeHtml(n.username)}</strong>
                  <span>${new Date(n.created_at).toLocaleString()}</span>
                </div>
                <div style="font-size:0.85rem; color:var(--text-main);">${this.escapeHtml(n.note_text)}</div>
              </div>
            `).join("") || `<span style="font-size:0.85rem; color:var(--text-muted);">No notes added yet.</span>`}
          </div>

          <div style="display:flex; gap:0.5rem;">
            <input type="text" id="input-new-note" class="form-input" placeholder="Add an internal estimate remark or specification note...">
            <button class="btn btn-primary btn-sm" onclick="App.addJobNote('${jobId}')">Add Note</button>
          </div>
        </div>
      `;

      bodyContainer.innerHTML = html;
    } catch (err) {
      bodyContainer.innerHTML = `<div style="color:var(--danger);">Failed to load enquiry content.</div>`;
    }
  },

  async changeJobStatus(jobId, newStatus) {
    try {
      await API.post(`/api/jobs/${encodeURIComponent(jobId)}/status`, { status: newStatus });
      API.showToast(`Status updated to ${newStatus}`, "info");
      this.loadJobs();
    } catch (e) {
      console.error(e);
    }
  },

  async addJobNote(jobId) {
    const input = document.getElementById("input-new-note");
    const noteText = input.value.trim();
    if (!noteText) return;

    try {
      await API.post(`/api/jobs/${encodeURIComponent(jobId)}/notes`, { note: noteText });
      input.value = "";
      API.showToast("Note attached to enquiry.", "info");
      this.openJobDetail(jobId);
    } catch (e) {
      console.error(e);
    }
  },

  closeModal() {
    document.getElementById("job-modal").classList.remove("active");
  },

  // ---------------------------------------------------------------------------
  // Mailboxes Control
  // ---------------------------------------------------------------------------

  async loadMailboxes() {
    const list = document.getElementById("mailboxes-list");
    list.innerHTML = `<div style="text-align:center; padding:1.5rem; color:var(--text-muted);">Loading mailboxes...</div>`;

    try {
      const data = await API.get("/api/mailboxes");
      if (!data || !data.mailboxes || data.mailboxes.length === 0) {
        list.innerHTML = `
          <div style="text-align:center; padding:2rem; background:var(--bg-body); border-radius:var(--radius-sm); border:1px dashed var(--border-color);">
            <div style="margin-bottom:0.5rem; color:var(--text-muted);">No dedicated mailbox accounts configured yet.</div>
            <button class="btn btn-primary btn-sm" onclick="App.openAddMailboxModal()">+ Add Inbound Mailbox</button>
          </div>
        `;
        return;
      }

      list.innerHTML = data.mailboxes.map(mb => {
        const statusBadge = mb.last_status === "CONNECTED"
          ? `<span class="badge badge-success">CONNECTED</span>`
          : (mb.last_status === "ERROR" ? `<span class="badge badge-danger">ERROR</span>` : `<span class="badge badge-muted">${mb.last_status}</span>`);

        const activeBadge = mb.is_active
          ? `<span style="color:var(--success); font-weight:600; font-size:0.8rem;">● Active</span>`
          : `<span style="color:var(--text-muted); font-size:0.8rem;">○ Inactive</span>`;

        return `
          <div class="attachment-card" style="padding:1rem;">
            <div class="attachment-meta">
              <span style="color:var(--primary);">${Icons.mail(22)}</span>
              <div>
                <div style="display:flex; align-items:center; gap:0.5rem;">
                  <strong style="color:var(--text-main); font-size:0.95rem;">${this.escapeHtml(mb.name)}</strong>
                  ${statusBadge}
                  ${activeBadge}
                </div>
                <div style="font-size:0.8rem; color:var(--text-muted); margin-top:0.25rem;">
                  ${this.escapeHtml(mb.username)} &bull; ${this.escapeHtml(mb.server)}:${mb.port} &bull; Folder: ${this.escapeHtml(mb.folder)} &bull; Interval: ${mb.poll_interval_seconds}s
                </div>
                ${mb.last_error ? `<div style="font-size:0.75rem; color:var(--danger); margin-top:0.25rem;">${this.escapeHtml(mb.last_error)}</div>` : ''}
              </div>
            </div>
            <div style="display:flex; gap:0.5rem;">
              <button class="btn btn-secondary btn-sm" onclick="App.testMailbox(${mb.id})">Test Connection</button>
              <button class="btn btn-secondary btn-sm" onclick="App.toggleMailbox(${mb.id})">${mb.is_active ? 'Deactivate' : 'Activate'}</button>
              <button class="btn btn-danger btn-sm" onclick="App.deleteMailbox(${mb.id})">Delete</button>
            </div>
          </div>
        `;
      }).join("");
    } catch (e) {
      list.innerHTML = `<div style="color:var(--danger);">Failed to load mailbox accounts.</div>`;
    }
  },

  openAddMailboxModal() {
    document.getElementById("mailbox-modal").classList.add("active");
  },

  async saveNewMailbox() {
    const payload = {
      name: document.getElementById("mb-name").value,
      server: document.getElementById("mb-server").value,
      port: parseInt(document.getElementById("mb-port").value, 10),
      use_ssl: document.getElementById("mb-ssl").checked,
      username: document.getElementById("mb-user").value,
      password: document.getElementById("mb-pass").value,
      folder: document.getElementById("mb-folder").value,
      poll_interval_seconds: parseInt(document.getElementById("mb-interval").value, 10)
    };

    try {
      await API.post("/api/mailboxes", payload);
      document.getElementById("mailbox-modal").classList.remove("active");
      document.getElementById("form-add-mailbox").reset();
      API.showToast("Mailbox account saved with encrypted credentials.", "info");
      this.loadMailboxes();
    } catch (e) {
      console.error(e);
    }
  },

  async testMailbox(id) {
    API.showToast("Testing IMAP connection...", "info");
    try {
      const res = await API.post(`/api/mailboxes/${id}/test`);
      API.showToast(res.message, res.success ? "info" : "danger");
      this.loadMailboxes();
    } catch (e) {
      console.error(e);
    }
  },

  async toggleMailbox(id) {
    try {
      const res = await API.post(`/api/mailboxes/${id}/toggle`);
      API.showToast(res.message, "info");
      this.loadMailboxes();
    } catch (e) {
      console.error(e);
    }
  },

  async deleteMailbox(id) {
    if (!confirm("Are you sure you want to remove this mailbox?")) return;
    try {
      await API.delete(`/api/mailboxes/${id}`);
      API.showToast("Mailbox removed.", "info");
      this.loadMailboxes();
    } catch (e) {
      console.error(e);
    }
  },

  // ---------------------------------------------------------------------------
  // Monitoring Daemon Control
  // ---------------------------------------------------------------------------

  async loadMonitoringStatus() {
    try {
      const data = await API.get("/api/monitoring/status");
      if (!data) return;

      const badge = document.getElementById("monitor-status-badge");
      badge.textContent = data.status;
      badge.className = `badge ${data.status === 'RUNNING' ? 'badge-success' : (data.status === 'PAUSED' ? 'badge-warning' : 'badge-danger')}`;

      document.getElementById("monitor-active-count").textContent = data.active_mailboxes_count;
      document.getElementById("monitor-last-sync").textContent = data.last_sync ? new Date(data.last_sync).toLocaleString() : "Never";
      document.getElementById("monitor-interval").textContent = `${data.poll_interval_seconds}s`;

      document.getElementById("btn-start-monitor").disabled = data.is_running;
      document.getElementById("btn-pause-monitor").disabled = !data.is_running || data.is_paused;
      document.getElementById("btn-resume-monitor").disabled = !data.is_running || !data.is_paused;
    } catch (e) {
      console.error(e);
    }
  },

  async controlMonitoring(action) {
    try {
      const res = await API.post(`/api/monitoring/${action}`);
      API.showToast(res.message, "info");
      this.loadMonitoringStatus();
    } catch (e) {
      console.error(e);
    }
  },

  // ---------------------------------------------------------------------------
  // Team & User Management
  // ---------------------------------------------------------------------------

  async loadTeamUsers() {
    const list = document.getElementById("team-users-list");
    list.innerHTML = `<div style="text-align:center; padding:1.5rem; color:var(--text-muted);">Loading team members...</div>`;

    try {
      const data = await API.get("/api/users");
      if (!data || !data.users) return;

      list.innerHTML = data.users.map(u => {
        const roleBadge = u.role === 'admin' ? 'badge-primary' : (u.role === 'estimator' ? 'badge-success' : 'badge-muted');
        const activeText = u.is_active ? `<span style="color:var(--success);">Active</span>` : `<span style="color:var(--danger);">Deactivated</span>`;

        return `
          <div class="attachment-card">
            <div class="attachment-meta">
              <span style="color:var(--primary);">${Icons.users(20)}</span>
              <div>
                <div style="display:flex; align-items:center; gap:0.5rem;">
                  <strong style="color:var(--text-main); font-size:0.9rem;">${this.escapeHtml(u.username)}</strong>
                  <span class="badge ${roleBadge}">${u.role.toUpperCase()}</span>
                  <span style="font-size:0.75rem;">${activeText}</span>
                </div>
                <div style="font-size:0.8rem; color:var(--text-muted);">${this.escapeHtml(u.full_name || '')} ${u.email ? '&bull; ' + this.escapeHtml(u.email) : ''}</div>
              </div>
            </div>
            <div style="display:flex; gap:0.5rem;">
              <select class="filter-select" style="padding:0.3rem 0.5rem; font-size:0.75rem;" onchange="App.changeUserRole(${u.id}, this.value)">
                <option value="admin" ${u.role === 'admin' ? 'selected' : ''}>Admin</option>
                <option value="estimator" ${u.role === 'estimator' ? 'selected' : ''}>Estimator</option>
                <option value="viewer" ${u.role === 'viewer' ? 'selected' : ''}>Viewer</option>
              </select>
              <button class="btn btn-secondary btn-sm" onclick="App.toggleUser(${u.id})">${u.is_active ? 'Deactivate' : 'Activate'}</button>
            </div>
          </div>
        `;
      }).join("");
    } catch (e) {
      list.innerHTML = `<div style="color:var(--danger);">Failed to load team users.</div>`;
    }
  },

  async saveNewUser() {
    const payload = {
      username: document.getElementById("new-username").value,
      full_name: document.getElementById("new-fullname").value,
      email: document.getElementById("new-email").value,
      password: document.getElementById("new-password").value,
      role: document.getElementById("new-role").value
    };

    try {
      await API.post("/api/users", payload);
      document.getElementById("user-modal").classList.remove("active");
      document.getElementById("form-add-user").reset();
      API.showToast("Team member added successfully.", "info");
      this.loadTeamUsers();
    } catch (e) {
      console.error(e);
    }
  },

  async changeUserRole(userId, newRole) {
    try {
      await API.request(`/api/users/${userId}/role`, { method: "PUT", body: JSON.stringify({ role: newRole }) });
      API.showToast("User role updated.", "info");
      this.loadTeamUsers();
    } catch (e) {
      console.error(e);
    }
  },

  async toggleUser(userId) {
    try {
      await API.post(`/api/users/${userId}/toggle`);
      API.showToast("User status updated.", "info");
      this.loadTeamUsers();
    } catch (e) {
      console.error(e);
    }
  },

  // ---------------------------------------------------------------------------
  // Quarantine & Filter Config
  // ---------------------------------------------------------------------------

  async loadQuarantine() {
    const listContainer = document.getElementById("quarantine-list");
    listContainer.innerHTML = `<div style="text-align:center; color:var(--text-muted); padding:1rem;">Loading quarantine items...</div>`;

    try {
      const data = await API.get("/api/quarantine");
      if (!data || !data.files || data.files.length === 0) {
        listContainer.innerHTML = `<div style="text-align:center; color:var(--success); padding:2rem; background:var(--success-subtle); border-radius:var(--radius-sm); border:1px solid var(--success-border);">✓ No suspicious threats in quarantine. All clear!</div>`;
        return;
      }

      listContainer.innerHTML = data.files.map(f => {
        const sizeKb = (f.size_bytes / 1024).toFixed(1);
        return `
          <div class="attachment-card">
            <div class="attachment-meta">
              <span style="color:var(--danger);">${Icons.shieldAlert(20)}</span>
              <div>
                <div style="font-weight:600; color:var(--danger); font-size:0.875rem;">${this.escapeHtml(f.filename)}</div>
                <div style="font-size:0.75rem; color:var(--text-muted);">${sizeKb} KB</div>
              </div>
            </div>
            <div style="display:flex; gap:0.5rem;">
              <a href="/api/quarantine/${encodeURIComponent(f.filename)}/download" class="btn btn-secondary btn-sm">Download for Analysis</a>
              <button onclick="App.deleteQuarantined('${this.escapeHtml(f.filename)}')" class="btn btn-danger btn-sm">Purge</button>
            </div>
          </div>
        `;
      }).join("");
    } catch (err) {
      listContainer.innerHTML = `<div style="color:var(--danger);">Failed to load quarantine list.</div>`;
    }
  },

  async deleteQuarantined(filename) {
    if (!confirm(`Permanently purge quarantined file '${filename}'?`)) return;
    try {
      await API.delete(`/api/quarantine/${encodeURIComponent(filename)}`);
      API.showToast("Quarantined file purged.", "info");
      this.loadQuarantine();
      this.loadStats();
    } catch (e) {
      console.error(e);
    }
  },

  async loadConfig() {
    try {
      const conf = await API.get("/api/config");
      if (!conf) return;

      document.getElementById("cfg-keywords").value = (conf.filters.required_subject_keywords || []).join(", ");
      document.getElementById("cfg-domains").value = (conf.filters.allowed_sender_domains || []).join(", ");
      document.getElementById("cfg-blocked").value = (conf.filters.blocked_sender_domains || []).join(", ");
      document.getElementById("cfg-intake").value = (conf.filters.intake_addresses || []).join(", ");
    } catch (e) {
      console.error(e);
    }
  },

  async saveFilterConfig() {
    const parseList = (val) => val.split(",").map(s => s.trim()).filter(Boolean);

    const payload = {
      required_subject_keywords: parseList(document.getElementById("cfg-keywords").value),
      allowed_sender_domains: parseList(document.getElementById("cfg-domains").value),
      blocked_sender_domains: parseList(document.getElementById("cfg-blocked").value),
      intake_addresses: parseList(document.getElementById("cfg-intake").value)
    };

    try {
      await API.post("/api/config/filters", payload);
      API.showToast("Filter rules saved and active.", "info");
    } catch (e) {
      console.error(e);
    }
  },

  async triggerSync() {
    const btn = document.getElementById("sync-now-btn");
    btn.disabled = true;
    btn.innerHTML = `${Icons.refresh(16)} Syncing...`;

    try {
      const res = await API.post("/api/monitoring/sync");
      API.showToast(res.message, "info");
      await this.loadStats();
      await this.loadJobs();
    } catch (e) {
      console.error(e);
    } finally {
      btn.disabled = false;
      btn.innerHTML = `${Icons.refresh(16)} Sync Mailboxes`;
    }
  },

  async logout() {
    await API.post("/api/auth/logout");
    window.location.href = "/login";
  },

  initEventStream() {
    if (!window.EventSource) return;
    const es = new EventSource("/api/events/stream");
    es.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload.type === "STATS_UPDATE") {
          this.loadStats();
        }
      } catch (e) {}
    };
  },

  escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  },

  renderSanitizedMarkdown(md) {
    if (!md) return "";
    let safe = this.escapeHtml(md);

    safe = safe.replace(/^### (.*$)/gim, '<h3>$1</h3>');
    safe = safe.replace(/^## (.*$)/gim, '<h2>$1</h2>');
    safe = safe.replace(/^# (.*$)/gim, '<h1>$1</h1>');
    safe = safe.replace(/\*\*(.*?)\*\*/gim, '<strong>$1</strong>');
    safe = safe.replace(/\*(.*?)\*/gim, '<em>$1</em>');
    safe = safe.replace(/`([^`]+)`/gim, '<code>$1</code>');
    safe = safe.replace(/^\> (.*$)/gim, '<blockquote>$1</blockquote>');
    safe = safe.replace(/\n\n/gim, '<p></p>');
    safe = safe.replace(/\n/gim, '<br>');

    return safe;
  }
};
