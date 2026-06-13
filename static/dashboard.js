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

function updateSummary(payload) {
  document.getElementById("summary-total-items").textContent = payload.total_items;
  document.getElementById("summary-active-downloads").textContent = payload.active_downloads;
  document.getElementById("summary-cache-size").textContent = formatBytes(payload.total_cache_bytes);

  const counts = payload.status_counts || {};
  const ready = counts.ready || 0;
  const pending = (counts.downloading || 0) + (counts.processing || 0) + (counts.queued || 0) + (counts.failed || 0) + (counts.missing || 0);
  document.getElementById("summary-ready-count").textContent = ready;
  document.getElementById("summary-pending-count").textContent = pending;
}

async function refresh() {
  const response = await fetch("/downloads?page=1&limit=1", {
    headers: { Accept: "application/json" },
  });
  const payload = await response.json();
  updateSummary(payload);
}

refresh();
setInterval(refresh, 10000);
