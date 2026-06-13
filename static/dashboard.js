const defaultLimit = 10;
let currentPage = 1;

function formatBytes(value) {
  if (value === null || value === undefined) return "unknown";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = value;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex++;
  }
  return `${size.toFixed(size >= 10 || unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

function formatSpeed(value) {
  if (value === null || value === undefined) return "unknown";
  return `${formatBytes(value)}/s`;
}

function formatTime(value) {
  if (!value) return "unknown";
  return new Date(value * 1000).toLocaleString();
}

function formatProgress(value) {
  if (value === null || value === undefined) return "unknown";
  return `${value.toFixed(2)}%`;
}

function formatStatusCounts(statusCounts) {
  const labels = Object.entries(statusCounts || {});
  if (!labels.length) return "-";
  return labels.map(([status, count]) => `${status}: ${count}`).join(" | ");
}

function statusColor(status) {
  const colors = {
    ready: "text-green-600 bg-green-50",
    downloading: "text-blue-600 bg-blue-50",
    processing: "text-yellow-600 bg-yellow-50",
    queued: "text-gray-600 bg-gray-100",
    failed: "text-red-600 bg-red-50",
    missing: "text-gray-400 bg-gray-50",
  };
  return colors[status] || colors.missing;
}

function progressColor(value) {
  if (value === null || value === undefined) return "bg-gray-200";
  if (value >= 100) return "bg-green-500";
  if (value > 0) return "bg-blue-500";
  return "bg-gray-200";
}

function updatePagination(payload) {
  document.getElementById("page-info").textContent = `Pagina ${payload.page} di ${payload.total_pages}`;
  document.getElementById("prev-page").disabled = payload.page <= 1;
  document.getElementById("next-page").disabled = payload.page >= payload.total_pages;
}

function updateSummary(payload) {
  document.getElementById("summary-total-items").textContent = payload.total_items;
  document.getElementById("summary-active-downloads").textContent = payload.active_downloads;
  document.getElementById("summary-cache-size").textContent = formatBytes(payload.total_cache_bytes);
  document.getElementById("summary-status-counts").textContent = formatStatusCounts(payload.status_counts);
}

function renderDownloads(payload) {
  const downloads = payload.downloads || [];
  const container = document.getElementById("downloads-list");

  if (!downloads.length) {
    container.innerHTML = '<p class="text-sm text-gray-400 py-4 text-center">Nessuna entry presente in cache.</p>';
    return;
  }

  container.innerHTML = downloads.map((d) => {
    const status = d.status || "missing";
    const progress = d.progress_percent ?? 0;
    const total = d.expected_bytes ? formatBytes(d.expected_bytes) : "unknown";
    const title = d.title || d.cache_key;
    const errorBlock = d.last_error
      ? `<div class="mt-2 rounded-md bg-red-50 p-2 text-xs text-red-700">${d.last_error}</div>`
      : "";

    return `<div class="rounded-lg border p-4 ${status === "ready" ? "bg-white" : status === "failed" ? "bg-red-50" : "bg-white"}">
      <div class="flex items-start justify-between">
        <div class="min-w-0 flex-1">
          <p class="text-sm font-medium text-gray-900 truncate">${title}</p>
          <p class="text-xs text-gray-500 truncate mt-0.5">${d.cache_key}</p>
        </div>
        <span class="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${statusColor(status)}">${status}</span>
      </div>
      <div class="mt-3 flex items-center gap-3">
        <div class="flex-1 h-2 rounded-full bg-gray-200 overflow-hidden">
          <div class="h-full rounded-full transition-all ${progressColor(progress)}" style="width: ${Math.max(0, Math.min(progress, 100))}%"></div>
        </div>
        <span class="text-xs text-gray-500 whitespace-nowrap">${formatProgress(d.progress_percent)}</span>
        <span class="text-xs text-gray-400 whitespace-nowrap">${formatSpeed(d.download_speed_bytes_per_second)}</span>
      </div>
      <div class="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-gray-500 sm:grid-cols-3">
        <span>Scaricato: ${formatBytes(d.downloaded_bytes)} / ${total}</span>
        <span>Tentativi: ${d.attempt}</span>
        <span>Ultimo progresso: ${formatTime(d.last_progress_at)}</span>
        <span>Creato: ${formatTime(d.created_at)}</span>
        <span>Completato: ${formatTime(d.completed_at)}</span>
        <span>Infohash: ${d.infohash} / ${d.index}</span>
      </div>
      ${errorBlock}
    </div>`;
  }).join("");
}

async function refresh() {
  const response = await fetch(`/downloads?page=${currentPage}&limit=${defaultLimit}`, {
    headers: { Accept: "application/json" },
  });
  const payload = await response.json();
  currentPage = payload.page;
  updateSummary(payload);
  updatePagination(payload);
  renderDownloads(payload);
}

document.getElementById("prev-page").addEventListener("click", async () => {
  if (currentPage <= 1) return;
  currentPage--;
  await refresh();
});

document.getElementById("next-page").addEventListener("click", async () => {
  currentPage++;
  await refresh();
});

refresh();
setInterval(refresh, 10000);
