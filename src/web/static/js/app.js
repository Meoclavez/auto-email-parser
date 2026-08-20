/**
 * Main Single Page Application Controller for the Email Parser Dashboard.
 */

document.addEventListener("DOMContentLoaded", () => {
  App.init();
});

const App = {
  currentUser: null,
  currentJob: null,
  activeTab: "jobs",
  searchTerm: "",
  statusFilter: "ALL",

  async init() {
    await this.checkAuth();
    this.setupEventListeners();
    await this.loadStats();
    await this.loadJobs();
    this.initEventStream();
  },

  async checkAuth() {
    try {
      const res = await API.get("/api/auth/me");
      if (res && res.authenticated) {
        this.currentUser = res.user;
        document.getElementById("user-name").textContent = this.currentUser.username;
        document.getElementById("user-role").textContent = `(${this.currentUser.role.toUpperCase()})`;
      }
    } catch (e) {
      window.location.href = "/login";
    }
  },

  setupEventListeners() {
    // Navigation Tabs
    document.querySelectorAll(".tab-btn").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const targetTab = e.target.dataset.tab;
        this.switchTab(targetTab);
      });
    });

    // Search input
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

    // Sync Now button
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

    // Close modal on click outside
    document.getElementById("job-modal").addEventListener("click", (e) => {
      if (e.target.id === "job-modal") this.closeModal();
    });

    // Save filters config button
    const saveFiltersBtn = document.getElementById("save-filters-btn");
    if (saveFiltersBtn) {
      saveFiltersBtn.addEventListener("click", () => this.saveFilterConfig());
    }
  },

  switchTab(tabName) {
    this.activeTab = tabName;
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
    document.querySelector(`.tab-btn[data-tab="${tabName}"]`).classList.add("active");

    document.getElementById("tab-jobs-view").style.display = tabName === "jobs" ? "block" : "none";
    document.getElementById("tab-quarantine-view").style.display = tabName === "quarantine" ? "block" : "none";
    document.getElementById("tab-config-view").style.display = tabName === "config" ? "block" : "none";

    if (tabName === "quarantine") this.loadQuarantine();
    if (tabName === "config") this.loadConfig();
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
    tableBody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:var(--text-muted);">Loading enquiries...</td></tr>`;

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
        let statusBadgeClass = "pill-muted";
        if (j.status === "PROCESSED") statusBadgeClass = "pill-success";
        else if (j.status === "FAILED") statusBadgeClass = "pill-danger";
        else if (j.status === "PENDING") statusBadgeClass = "pill-warning";

        const timeStr = j.updated_at ? new Date(j.updated_at).toLocaleString() : "-";

        return `
          <tr onclick="App.openJobDetail('${j.job_id || j.message_id}')">
            <td><strong>${this.escapeHtml(j.job_id || "PENDING")}</strong></td>
            <td>${this.escapeHtml(j.sender || "Unknown")}</td>
            <td>${this.escapeHtml(j.subject || "(No Subject)")}</td>
            <td><span class="pill-status ${statusBadgeClass}">${j.status}</span></td>
            <td style="color:var(--text-muted); font-size:0.8rem;">${timeStr}</td>
          </tr>
        `;
      }).join("");

    } catch (err) {
      tableBody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:var(--accent-danger);">Failed to load jobs.</td></tr>`;
    }
  },

  async openJobDetail(jobId) {
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
      let html = "";

      // Attachments Section
      if (manifest && manifest.attachments && manifest.attachments.length > 0) {
        html += `<h4 style="margin-bottom:0.75rem; color:#fff;">📎 Downloadable Attachments</h4><div style="margin-bottom:1.5rem;">`;
        manifest.attachments.forEach(att => {
          const downloadUrl = `/api/jobs/${encodeURIComponent(jobId)}/attachments/${encodeURIComponent(att.filename)}`;
          const sizeKb = (att.size_bytes / 1024).toFixed(1);
          html += `
            <div class="attachment-card">
              <div class="attachment-info">
                <span class="attachment-icon">📄</span>
                <div>
                  <div style="font-weight:600; color:#fff;">${this.escapeHtml(att.filename)}</div>
                  <div style="font-size:0.75rem; color:var(--text-muted);">${sizeKb} KB • SHA-256: ${att.sha256 ? att.sha256.substring(0, 10) + '...' : 'N/A'}</div>
                </div>
              </div>
              <a href="${downloadUrl}" class="btn btn-primary btn-sm" download>⬇ Download</a>
            </div>
          `;
        });
        html += `</div>`;
      }

      // Quarantined warnings
      if (manifest && manifest.quarantined_attachments && manifest.quarantined_attachments.length > 0) {
        html += `<div style="background:rgba(239, 68, 68, 0.15); border:1px solid rgba(239,68,68,0.3); border-radius:6px; padding:1rem; margin-bottom:1.5rem;">
          <strong style="color:var(--accent-danger);">⚠️ Quarantined Threats Detected:</strong>
          <ul style="margin-left:1.25rem; margin-top:0.5rem; color:var(--text-primary);">`;
        manifest.quarantined_attachments.forEach(qa => {
          html += `<li><strong>${this.escapeHtml(qa.original_name)}</strong>: ${this.escapeHtml(qa.reason)}</li>`;
        });
        html += `</ul></div>`;
      }

      // Rendered Markdown Body
      if (mdData && mdData.content) {
        html += `<h4 style="margin-bottom:0.75rem; color:#fff;">📝 Email Markdown Content</h4>`;
        html += `<div class="markdown-preview">${this.renderSanitizedMarkdown(mdData.content)}</div>`;
      }

      bodyContainer.innerHTML = html;
    } catch (err) {
      bodyContainer.innerHTML = `<div style="color:var(--accent-danger);">Failed to load enquiry content.</div>`;
    }
  },

  closeModal() {
    document.getElementById("job-modal").classList.remove("active");
  },

  async loadQuarantine() {
    const listContainer = document.getElementById("quarantine-list");
    listContainer.innerHTML = `<div style="text-align:center; color:var(--text-muted);">Loading quarantine items...</div>`;

    try {
      const data = await API.get("/api/quarantine");
      if (!data || !data.files || data.files.length === 0) {
        listContainer.innerHTML = `<div style="text-align:center; color:var(--accent-success); padding:2rem;">✓ No suspicious files in quarantine. All clear!</div>`;
        return;
      }

      listContainer.innerHTML = data.files.map(f => {
        const sizeKb = (f.size_bytes / 1024).toFixed(1);
        return `
          <div class="attachment-card">
            <div class="attachment-info">
              <span class="attachment-icon">☣️</span>
              <div>
                <div style="font-weight:600; color:var(--accent-danger);">${this.escapeHtml(f.filename)}</div>
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
      listContainer.innerHTML = `<div style="color:var(--accent-danger);">Failed to load quarantine list.</div>`;
    }
  },

  async deleteQuarantined(filename) {
    if (!confirm(`Are you sure you want to permanently delete '${filename}'?`)) return;
    try {
      await API.delete(`/api/quarantine/${encodeURIComponent(filename)}`);
      API.showToast("Quarantined file purged successfully.", "info");
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
    const parseList = (val) => val.split(",").map(s => s.strip ? s.strip() : s.trim()).filter(Boolean);

    const payload = {
      required_subject_keywords: parseList(document.getElementById("cfg-keywords").value),
      allowed_sender_domains: parseList(document.getElementById("cfg-domains").value),
      blocked_sender_domains: parseList(document.getElementById("cfg-blocked").value),
      intake_addresses: parseList(document.getElementById("cfg-intake").value)
    };

    try {
      await API.post("/api/config/filters", payload);
      API.showToast("Filter rules saved and applied live.", "info");
    } catch (e) {
      console.error(e);
    }
  },

  async triggerSync() {
    const btn = document.getElementById("sync-now-btn");
    btn.disabled = true;
    btn.textContent = "Syncing...";

    try {
      const res = await API.post("/api/service/sync-now");
      API.showToast(res.message, "info");
      await this.loadStats();
      await this.loadJobs();
    } catch (e) {
      console.error(e);
    } finally {
      btn.disabled = false;
      btn.textContent = "🔄 Sync Mailbox";
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

    // Basic markdown formatting conversion safely
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
