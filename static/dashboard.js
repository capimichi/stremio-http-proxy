function formatBytes(value) {
  if (value === null || value === undefined) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = value;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex++;
  }
  return `${size.toFixed(size >= 10 || unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

function formatSpeed(bytesPerSec) {
  if (!bytesPerSec || bytesPerSec <= 0) return "";
  const mbps = (bytesPerSec / (1024 * 1024)).toFixed(2);
  return `${mbps} MB/s`;
}

function formatTime(value) {
  if (!value) return "-";
  return new Date(value * 1000).toLocaleString();
}

function formatProgress(value) {
  if (value === null || value === undefined) return "-";
  return `${value.toFixed(1)}%`;
}

function statusBadgeClasses(status) {
  const map = {
    ready: "bg-green-100 text-green-800",
    downloading: "bg-blue-100 text-blue-800",
    processing: "bg-yellow-100 text-yellow-800",
    queued: "bg-gray-100 text-gray-700",
    failed: "bg-red-100 text-red-800",
    missing: "bg-gray-50 text-gray-400",
  };
  return map[status] || map.missing;
}

function updateSummary(payload) {
  const totalEl = document.getElementById("summary-total-items");
  if (totalEl) totalEl.textContent = payload.total_items;

  const activeEl = document.getElementById("summary-active-downloads");
  if (activeEl) activeEl.textContent = payload.active_downloads;

  const cacheEl = document.getElementById("summary-cache-size");
  if (cacheEl) cacheEl.textContent = formatBytes(payload.total_cache_bytes);

  const counts = payload.status_counts || {};
  const ready = counts.ready || 0;
  const readyEl = document.getElementById("summary-ready-count");
  if (readyEl) readyEl.textContent = ready;

  const pending = (counts.downloading || 0) + (counts.processing || 0) + (counts.queued || 0) + (counts.failed || 0) + (counts.missing || 0);
  const pendingEl = document.getElementById("summary-pending-count");
  if (pendingEl) pendingEl.textContent = pending;
}

function renderTable(items, isActive) {
  const tbody = document.getElementById("active-downloads-body");
  const badge = document.getElementById("active-downloads-badge");
  const titleEl = document.getElementById("active-downloads-title");
  if (!tbody) return;

  if (titleEl) {
    titleEl.textContent = isActive ? "Download in corso" : "Ultimi download completati";
  }

  if (badge) {
    badge.textContent = isActive ? items.length : "0";
    if (isActive && items.length > 0) {
      badge.className = "inline-flex items-center rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-medium text-blue-800 animate-pulse";
    } else {
      badge.className = "inline-flex items-center rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-600";
    }
  }

  if (!items || items.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6" class="px-5 py-8 text-center text-sm text-gray-400">
          <div class="flex flex-col items-center justify-center gap-1.5">
            <i class="fa-solid fa-circle-check text-green-500 text-2xl"></i>
            <span class="font-medium text-gray-600">Nessun download attivo al momento.</span>
            <span class="text-xs text-gray-400">Tutti i contenuti accodati sono pronti in cache.</span>
          </div>
        </td>
      </tr>`;
    return;
  }

  tbody.innerHTML = items.map((d) => {
    const title = d.title || d.cache_key;
    const size = d.status === "ready"
      ? formatBytes(d.downloaded_bytes)
      : (d.expected_bytes ? `${formatBytes(d.downloaded_bytes)} / ${formatBytes(d.expected_bytes)}` : formatBytes(d.downloaded_bytes));
    const speed = formatSpeed(d.download_speed_bytes_per_second);
    const pct = Math.max(0, Math.min(d.progress_percent ?? 0, 100));

    return `<tr class="hover:bg-gray-50 transition-colors">
      <td class="px-5 py-3 text-sm font-medium text-gray-900 max-w-xs truncate" title="${title}">
        ${title}
      </td>
      <td class="px-5 py-3 text-sm text-gray-600 whitespace-nowrap">${size}</td>
      <td class="px-5 py-3">
        <span class="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${statusBadgeClasses(d.status)}">
          ${d.status}
        </span>
      </td>
      <td class="px-5 py-3 text-sm text-gray-600 whitespace-nowrap">
        <div class="flex flex-col gap-1">
          <div class="flex items-center gap-2">
            <div class="w-24 h-1.5 rounded-full bg-gray-200 overflow-hidden">
              <div class="h-full rounded-full ${d.status === "ready" ? "bg-green-500" : "bg-blue-500"}" style="width: ${pct}%"></div>
            </div>
            <span class="font-medium">${formatProgress(d.progress_percent)}</span>
          </div>
          ${speed ? `<span class="text-xs text-gray-400"><i class="fa-solid fa-arrow-down mr-1"></i>${speed}</span>` : ""}
        </div>
      </td>
      <td class="px-5 py-3 text-sm text-gray-500 whitespace-nowrap">${formatTime(d.created_at)}</td>
      <td class="px-5 py-3 whitespace-nowrap">
        <a href="/dashboard/cache-entry/${d.infohash}/${d.index}" class="inline-flex items-center gap-1 rounded-md border border-gray-300 bg-white px-2.5 py-1 text-xs font-medium text-gray-700 shadow-sm hover:bg-gray-50 transition-colors">
          Apri
        </a>
      </td>
    </tr>`;
  }).join("");
}

async function refresh() {
  try {
    const res = await fetch("/downloads?page=1&limit=5", {
      headers: { Accept: "application/json" },
    });
    if (res.ok) {
      const payload = await res.json();
      updateSummary(payload);

      if (payload.active_items && payload.active_items.length > 0) {
        renderTable(payload.active_items, true);
      } else {
        renderTable(payload.downloads, false);
      }
    }
  } catch (err) {
    console.error("Errore aggiornamento dashboard:", err);
  }
}

refresh();
setInterval(refresh, 3000);


