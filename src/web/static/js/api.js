/**
 * Authenticated API Fetch client with error handling and toast notifications.
 */

const API = {
  async request(url, options = {}) {
    const defaultHeaders = {
      "Accept": "application/json",
      "Content-Type": "application/json"
    };

    options.headers = { ...defaultHeaders, ...options.headers };

    try {
      const response = await fetch(url, options);

      // Handle session expiration
      if (response.status === 401) {
        window.location.href = "/login";
        return null;
      }

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        const errorMsg = data.message || data.error || `HTTP ${response.status} Error`;
        API.showToast(errorMsg, "danger");
        throw new Error(errorMsg);
      }

      return data;
    } catch (err) {
      console.error(`API Error [${url}]:`, err);
      throw err;
    }
  },

  get(url) {
    return this.request(url, { method: "GET" });
  },

  post(url, body = {}) {
    return this.request(url, {
      method: "POST",
      body: JSON.stringify(body)
    });
  },

  delete(url) {
    return this.request(url, { method: "DELETE" });
  },

  showToast(message, type = "info") {
    const container = document.getElementById("toast-container");
    if (!container) return;

    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `<span>${message}</span>`;

    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = "0";
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }
};
