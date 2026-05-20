const defaultLimit = 10;
let currentPage = 1;

function formatBytes(value) {
  if (value === null || value === undefined) {
    return "unknown";
  }
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = value;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }
  return `${size.toFixed(size >= 10 || unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

function formatSpeed(value) {
  if (value === null || value === undefined) {
    return "unknown";
  }
  return `${formatBytes(value)}/s`;
}

function formatTime(value) {
  if (!value) {
    return "unknown";
  }
  return new Date(value * 1000).toLocaleString();
}

function formatProgress(value) {
  if (value === null || value === undefined) {
    return "unknown";
  }
  return `${value.toFixed(2)}%`;
}

function formatStatusCounts(statusCounts) {
  const labels = Object.entries(statusCounts || {});
  if (!labels.length) {
    return "-";
  }
  return labels.map(([status, count]) => `${status}: ${count}`).join(" | ");
}

function getSpeedClass(value) {
  if (!value || value < 1024 * 1024) {
    return "speed-slow";
  }
  if (value < 5 * 1024 * 1024) {
    return "speed-medium";
  }
  return "speed-fast";
}

function getStatusClass(status) {
  return `status-${status || "missing"}`;
}

function getCardClass(status) {
  if (status === "downloading" || status === "processing") {
    return "is-active";
  }
  if (status === "ready") {
    return "is-ready";
  }
  if (status === "failed") {
    return "is-failed";
  }
  return "";
}

function updatePagination(payload) {
  const pageInfo = document.getElementById("page-info");
  const previousButton = document.getElementById("prev-page");
  const nextButton = document.getElementById("next-page");
  pageInfo.textContent = `Pagina ${payload.page} di ${payload.total_pages}`;
  previousButton.disabled = payload.page <= 1;
  nextButton.disabled = payload.page >= payload.total_pages;
}

function updateSummary(payload) {
  document.getElementById("summary-total-items").textContent = payload.total_items;
  document.getElementById("summary-active-downloads").textContent = payload.active_downloads;
  document.getElementById("summary-cache-size").textContent = formatBytes(payload.total_cache_bytes);
  document.getElementById("summary-status-counts").textContent = formatStatusCounts(payload.status_counts);
}

function createMetric(label, value) {
  return `
    <div class="metric">
      <span class="metric-label">${label}</span>
      <span class="metric-value">${value}</span>
    </div>
  `;
}

function renderDownloads(payload) {
  const downloads = payload.downloads || [];
  const container = document.getElementById("downloads");

  if (!downloads.length) {
    container.innerHTML = '<p class="empty">Nessuna entry presente in cache.</p>';
    updatePagination(payload);
    updateSummary(payload);
    return;
  }

  container.innerHTML = downloads.map((download) => {
    const status = download.status || "missing";
    const progressValue = download.progress_percent ?? 0;
    const total = download.expected_bytes ? formatBytes(download.expected_bytes) : "unknown";
    const title = download.title || download.cache_key;
    const errorBlock = download.last_error
      ? `
          <div class="error-box">
            <span class="metric-label">Ultimo errore</span>
            <span class="metric-value">${download.last_error}</span>
          </div>
        `
      : "";

    return `
      <article class="download-card ${getCardClass(status)}">
        <div class="download-header">
          <div>
            <h3 class="download-title">${title}</h3>
            <p class="download-key">${download.cache_key}</p>
          </div>
          <span class="status-badge ${getStatusClass(status)}">${status}</span>
        </div>

        <div class="progress-row">
          <div class="progress-track">
            <div class="progress-fill" style="width: ${Math.max(0, Math.min(progressValue, 100))}%"></div>
          </div>
          <span class="progress-value">${formatProgress(download.progress_percent)}</span>
          <span class="speed-indicator ${getSpeedClass(download.download_speed_bytes_per_second)}">${formatSpeed(download.download_speed_bytes_per_second)}</span>
        </div>

        <div class="metrics-grid">
          ${createMetric("Scaricato", `${formatBytes(download.downloaded_bytes)} / ${total}`)}
          ${createMetric("Tentativi", download.attempt)}
          ${createMetric("Ultimo progresso", formatTime(download.last_progress_at))}
          ${createMetric("Creato", formatTime(download.created_at))}
          ${createMetric("Completato", formatTime(download.completed_at))}
          ${createMetric("Infohash / Index", `${download.infohash} / ${download.index}`)}
        </div>
        ${errorBlock}
      </article>
    `;
  }).join("");

  updatePagination(payload);
  updateSummary(payload);
}

async function refresh() {
  const response = await fetch(`/downloads?page=${currentPage}&limit=${defaultLimit}`, {
    headers: { Accept: "application/json" },
  });
  const payload = await response.json();
  const manifestLink = document.getElementById("manifest-url");
  manifestLink.href = payload.manifest_url;
  manifestLink.textContent = payload.manifest_url;
  currentPage = payload.page;
  renderDownloads(payload);
}

document.getElementById("prev-page").addEventListener("click", async () => {
  if (currentPage <= 1) {
    return;
  }
  currentPage -= 1;
  await refresh();
});

document.getElementById("next-page").addEventListener("click", async () => {
  currentPage += 1;
  await refresh();
});

refresh();
setInterval(refresh, 10000);
