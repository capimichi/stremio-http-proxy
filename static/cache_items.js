const pageLimit = 20;
let currentPage = 1;
let searchTerm = "";
let currentStatus = "";
let debounceTimer = null;

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

function formatTime(value) {
  if (!value) return "-";
  return new Date(value * 1000).toLocaleString("it-IT", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatProgress(value) {
  if (value === null || value === undefined) return "-";
  return `${value.toFixed(1)}%`;
}

function statusBadgeHtml(status) {
  switch (status) {
    case "ready":
      return `<span class="inline-flex items-center gap-1 rounded-md bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 text-[11px] font-semibold text-emerald-400">
        <i class="fa-solid fa-check text-[9px]"></i> Pronto
      </span>`;
    case "downloading":
      return `<span class="inline-flex items-center gap-1 rounded-md bg-sky-500/10 border border-sky-500/20 px-2 py-0.5 text-[11px] font-semibold text-sky-400 animate-pulse">
        <i class="fa-solid fa-arrow-down text-[9px]"></i> Download
      </span>`;
    case "processing":
    case "queued":
      return `<span class="inline-flex items-center gap-1 rounded-md bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 text-[11px] font-semibold text-amber-400">
        <i class="fa-solid fa-clock text-[9px]"></i> In coda
      </span>`;
    case "failed":
      return `<span class="inline-flex items-center gap-1 rounded-md bg-rose-500/10 border border-rose-500/20 px-2 py-0.5 text-[11px] font-semibold text-rose-400">
        <i class="fa-solid fa-xmark text-[9px]"></i> Errore
      </span>`;
    default:
      return `<span class="inline-flex items-center gap-1 rounded-md bg-slate-800 border border-slate-700 px-2 py-0.5 text-[11px] font-medium text-slate-400">
        ${status}
      </span>`;
  }
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
    tbody.innerHTML = '<tr><td colspan="7" class="px-5 py-8 text-center text-slate-500 text-xs">Nessun elemento in cache trovato per i filtri selezionati.</td></tr>';
    return;
  }

  tbody.innerHTML = items.map((d) => {
    const title = d.title || d.cache_key;
    const size = d.status === "ready"
      ? formatBytes(d.downloaded_bytes)
      : (d.expected_bytes ? `${formatBytes(d.downloaded_bytes)} / ${formatBytes(d.expected_bytes)}` : formatBytes(d.downloaded_bytes));
    const shortHash = d.infohash.length > 14 ? d.infohash.slice(0, 14) + "…" : d.infohash;
    const pct = Math.max(0, Math.min(d.progress_percent ?? 0, 100));

    return `<tr class="hover:bg-slate-800/40 transition-colors">
      <td class="px-5 py-3 text-xs font-semibold text-slate-200 max-w-xs truncate" title="${title}">
        ${title}
      </td>
      <td class="px-5 py-3 text-slate-400 whitespace-nowrap font-mono text-xs">${size}</td>
      <td class="px-5 py-3 whitespace-nowrap">${statusBadgeHtml(d.status)}</td>
      <td class="px-5 py-3 text-slate-400 whitespace-nowrap">
        <div class="flex items-center gap-2">
          <div class="w-20 h-1.5 rounded-full bg-slate-800 overflow-hidden">
            <div class="h-full rounded-full ${d.status === "ready" ? "bg-emerald-500" : "bg-gradient-to-r from-indigo-500 to-sky-400"}" style="width: ${pct}%"></div>
          </div>
          <span class="font-mono text-xs text-slate-300 font-semibold">${formatProgress(d.progress_percent)}</span>
        </div>
      </td>
      <td class="px-5 py-3 text-slate-500 whitespace-nowrap font-mono text-[11px]">${formatTime(d.created_at)}</td>
      <td class="px-5 py-3 text-slate-500 font-mono text-[11px] whitespace-nowrap" title="${d.infohash}">${shortHash}</td>
      <td class="px-5 py-3 text-right whitespace-nowrap">
        <div class="flex items-center justify-end gap-2">
          <a href="/dashboard/cache-entry/${d.infohash}/${d.index}" class="inline-flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-800 hover:bg-slate-700 px-2.5 py-1 text-xs font-medium text-slate-300 transition-colors">
            Dettagli
          </a>
          <button
            class="delete-stream-btn inline-flex items-center justify-center rounded-lg border border-rose-900/40 bg-rose-950/20 hover:bg-rose-900/40 text-rose-400 hover:text-rose-300 p-1.5 transition-colors"
            data-key="${d.cache_key}"
            title="Elimina file dalla cache"
          >
            <i class="fa-solid fa-trash text-[11px]"></i>
          </button>
        </div>
      </td>
    </tr>`;
  }).join("");

  document.querySelectorAll(".delete-stream-btn").forEach((btn) => {
    btn.addEventListener("click", async function () {
      const key = this.dataset.key;
      if (!confirm(`Sei sicuro di voler eliminare questo flusso dalla cache?\n${key}`)) return;

      try {
        const resp = await fetch(`/api/hub/streams/${encodeURIComponent(key)}`, {
          method: "DELETE",
        });
        if (resp.ok) {
          refresh();
        } else {
          alert("Errore durante l'eliminazione.");
        }
      } catch (err) {
        alert("Errore di rete: " + err);
      }
    });
  });
}

async function refresh() {
  const params = new URLSearchParams({ page: currentPage, limit: pageLimit });
  if (searchTerm) params.set("search", searchTerm);
  if (currentStatus) params.set("status", currentStatus);

  try {
    const response = await fetch(`/downloads?${params}`, {
      headers: { Accept: "application/json" },
    });
    const payload = await response.json();
    currentPage = payload.page;
    updatePagination(payload);
    renderTable(payload);
  } catch (err) {
    console.error("Errore fetch cache items:", err);
  }
}

// Search input
document.getElementById("search-input").addEventListener("input", (e) => {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => {
    searchTerm = e.target.value.trim();
    currentPage = 1;
    refresh();
  }, 300);
});

// Pagination
document.getElementById("cache-prev-page").addEventListener("click", async () => {
  if (currentPage <= 1) return;
  currentPage--;
  await refresh();
});

document.getElementById("cache-next-page").addEventListener("click", async () => {
  currentPage++;
  await refresh();
});

// Filter Tabs
document.querySelectorAll(".status-tab-btn").forEach((btn) => {
  btn.addEventListener("click", function () {
    document.querySelectorAll(".status-tab-btn").forEach((b) => {
      b.className = "status-tab-btn px-3 py-1.5 rounded-lg font-semibold transition-colors bg-slate-800 text-slate-400 hover:text-white";
    });
    this.className = "status-tab-btn px-3 py-1.5 rounded-lg font-semibold transition-colors bg-indigo-600 text-white";
    currentStatus = this.dataset.status;
    currentPage = 1;
    refresh();
  });
});

refresh();
