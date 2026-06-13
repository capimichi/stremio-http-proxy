const pageLimit = 20;
let currentPage = 1;
let searchTerm = "";
let debounceTimer = null;

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

function updatePagination(payload) {
  document.getElementById("cache-page-info").textContent = `Pagina ${payload.page} di ${payload.total_pages}`;
  document.getElementById("cache-prev-page").disabled = payload.page <= 1;
  document.getElementById("cache-next-page").disabled = payload.page >= payload.total_pages;
}

function renderTable(payload) {
  const items = payload.downloads || [];
  const tbody = document.getElementById("cache-table-body");

  if (!items.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="px-5 py-8 text-center text-sm text-gray-400">Nessun elemento trovato.</td></tr>';
    return;
  }

  tbody.innerHTML = items.map((d) => {
    const title = d.title || d.cache_key;
    const size = d.status === "ready" ? formatBytes(d.downloaded_bytes) : (d.expected_bytes ? `${formatBytes(d.downloaded_bytes)} / ${formatBytes(d.expected_bytes)}` : formatBytes(d.downloaded_bytes));
    return `<tr class="hover:bg-gray-50">
      <td class="px-5 py-3 text-sm font-medium text-gray-900 max-w-xs truncate" title="${title}">${title}</td>
      <td class="px-5 py-3 text-sm text-gray-600 whitespace-nowrap">${size}</td>
      <td class="px-5 py-3"><span class="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${statusBadgeClasses(d.status)}">${d.status}</span></td>
      <td class="px-5 py-3 text-sm text-gray-600 whitespace-nowrap">
        <div class="flex items-center gap-2">
          <div class="w-20 h-1.5 rounded-full bg-gray-200 overflow-hidden">
            <div class="h-full rounded-full ${d.progress_percent === 100 ? "bg-green-500" : "bg-blue-500"}" style="width: ${Math.max(0, Math.min(d.progress_percent ?? 0, 100))}%"></div>
          </div>
          <span>${formatProgress(d.progress_percent)}</span>
        </div>
      </td>
      <td class="px-5 py-3 text-sm text-gray-500 whitespace-nowrap">${formatTime(d.created_at)}</td>
      <td class="px-5 py-3 text-xs text-gray-400 font-mono max-w-[120px] truncate" title="${d.infohash}">${d.infohash}</td>
      <td class="px-5 py-3 whitespace-nowrap">
        <a href="/dashboard/cache-entry/${d.infohash}/${d.index}" class="inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50 transition-colors">
          Apri
        </a>
      </td>
    </tr>`;
  }).join("");
}

async function refresh() {
  const params = new URLSearchParams({ page: currentPage, limit: pageLimit });
  if (searchTerm) params.set("search", searchTerm);

  const response = await fetch(`/downloads?${params}`, {
    headers: { Accept: "application/json" },
  });
  const payload = await response.json();
  currentPage = payload.page;
  updatePagination(payload);
  renderTable(payload);
}

document.getElementById("search-input").addEventListener("input", (e) => {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => {
    searchTerm = e.target.value.trim();
    currentPage = 1;
    refresh();
  }, 300);
});

document.getElementById("cache-prev-page").addEventListener("click", async () => {
  if (currentPage <= 1) return;
  currentPage--;
  await refresh();
});

document.getElementById("cache-next-page").addEventListener("click", async () => {
  currentPage++;
  await refresh();
});

refresh();
