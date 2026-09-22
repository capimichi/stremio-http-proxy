let allLibraryItems = [];
let currentFilterType = "all";
let cachedOnly = false;
let searchQuery = "";

const placeholderSvg = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 150 220'%3E%3Crect fill='%231e293b' width='150' height='220'/%3E%3Ctext x='50%25' y='50%25' dominant-baseline='middle' text-anchor='middle' fill='%2364748b' font-family='sans-serif' font-size='12'%3ENo Poster%3C/text%3E%3C/svg%3E";

function timeAgo(timestamp) {
  if (!timestamp) return "";
  const seconds = Math.floor(Date.now() / 1000 - timestamp);
  if (seconds < 60) return "Poco fa";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m fa`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h fa`;
  const days = Math.floor(hours / 24);
  return `${days}gg fa`;
}

async function loadLibrary() {
  const loadingEl = document.getElementById("library-loading");
  const gridEl = document.getElementById("library-grid");
  const emptyEl = document.getElementById("library-empty");

  try {
    let url = "/api/hub/library?limit=500";
    if (currentFilterType !== "all") {
      url += `&type=${currentFilterType}`;
    }
    if (cachedOnly) {
      url += `&cached_only=true`;
    }

    const res = await fetch(url, { headers: { Accept: "application/json" } });
    if (!res.ok) throw new Error("Errore nel caricamento della libreria");

    const data = await res.json();
    allLibraryItems = data.items || [];

    const totalBadge = document.getElementById("library-total-badge");
    if (totalBadge) {
      totalBadge.textContent = `${data.total || allLibraryItems.length} titoli`;
    }

    if (loadingEl) loadingEl.classList.add("hidden");
    filterAndRender();
  } catch (err) {
    console.error("Errore libreria:", err);
    if (loadingEl) loadingEl.classList.add("hidden");
    if (gridEl) gridEl.classList.add("hidden");
    if (emptyEl) {
      emptyEl.classList.remove("hidden");
      document.getElementById("empty-title").textContent = "Impossibile caricare la libreria";
      document.getElementById("empty-subtext").textContent = err.message || "Errore di connessione al proxy.";
    }
  }
}

function filterAndRender() {
  const gridEl = document.getElementById("library-grid");
  const emptyEl = document.getElementById("library-empty");

  let filtered = allLibraryItems;

  if (searchQuery.trim()) {
    const q = searchQuery.toLowerCase().trim();
    filtered = filtered.filter((item) => {
      const matchTitle = item.title && item.title.toLowerCase().includes(q);
      const matchYear = item.year && item.year.includes(q);
      const matchId = item.id && item.id.toLowerCase().includes(q);
      return matchTitle || matchYear || matchId;
    });
  }

  if (filtered.length === 0) {
    if (gridEl) gridEl.classList.add("hidden");
    if (emptyEl) {
      emptyEl.classList.remove("hidden");
      if (searchQuery.trim() || cachedOnly || currentFilterType !== "all") {
        document.getElementById("empty-title").textContent = "Nessun risultato con i filtri attuali";
        document.getElementById("empty-subtext").textContent = "Prova a modificare i termini di ricerca o a disattivare i filtri.";
      } else {
        document.getElementById("empty-title").textContent = "La tua libreria è vuota";
        document.getElementById("empty-subtext").textContent = "I titoli vengono aggiunti automaticamente qui quando riproduci uno stream o cerchi contenuti.";
      }
    }
    return;
  }

  if (emptyEl) emptyEl.classList.add("hidden");
  if (gridEl) {
    gridEl.classList.remove("hidden");
    gridEl.innerHTML = filtered.map((item) => renderMediaCard(item)).join("");
  }
}

function renderMediaCard(item) {
  const isSeries = item.type === "series";
  const typeBadge = isSeries ? "Serie TV" : "Film";
  const poster = item.poster || placeholderSvg;

  // Cache Badge Logic
  let cacheBadge = "";
  if (item.ready_streams_count > 0) {
    const countLabel = isSeries && item.cached_episodes_count > 0 
      ? `${item.cached_episodes_count} ep pronti`
      : `${item.ready_streams_count} file pronto`;
    cacheBadge = `
      <span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 text-[10px] font-bold backdrop-blur">
        <i class="fa-solid fa-circle-check text-[9px]"></i>
        <span>${countLabel}</span>
      </span>`;
  } else if (item.is_downloading) {
    cacheBadge = `
      <span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-sky-500/20 text-sky-400 border border-sky-500/30 text-[10px] font-bold animate-pulse backdrop-blur">
        <i class="fa-solid fa-arrow-down text-[9px]"></i>
        <span>Download in corso</span>
      </span>`;
  } else {
    cacheBadge = `
      <span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-slate-800/80 text-slate-400 border border-slate-700/60 text-[10px] font-medium backdrop-blur">
        Non in cache
      </span>`;
  }

  const stremioHref = item.stremio_url || `stremio://detail/${item.type}/${item.id}`;

  return `
    <div class="group relative rounded-2xl bg-slate-900 border border-slate-800 hover:border-indigo-500/50 p-2.5 transition-all duration-200 hover:scale-[1.02] flex flex-col justify-between shadow-lg hover:shadow-indigo-500/10">
      
      <!-- Poster container -->
      <div class="relative w-full aspect-[2/3] rounded-xl overflow-hidden bg-slate-950 border border-slate-800/60">
        <img
          src="${poster}"
          alt="${item.title}"
          class="w-full h-full object-cover group-hover:opacity-95 transition-opacity"
          loading="lazy"
          onerror="this.src='${placeholderSvg}'"
        >

        <!-- Top Badges -->
        <div class="absolute top-2 left-2 flex flex-col gap-1 items-start pointer-events-none">
          <span class="px-2 py-0.5 rounded bg-black/80 backdrop-blur text-[10px] font-bold text-slate-200 shadow">
            ${typeBadge}
          </span>
        </div>

        <div class="absolute top-2 right-2 pointer-events-none">
          ${cacheBadge}
        </div>

        <!-- Hover Quick Actions Overlay -->
        <div class="absolute inset-0 bg-slate-950/80 backdrop-blur-sm opacity-0 group-hover:opacity-100 transition-opacity flex flex-col items-center justify-center gap-2 p-3 text-center">
          <a
            href="/dashboard/browser/media/${item.id}"
            class="w-full inline-flex items-center justify-center gap-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 px-3 py-1.5 text-xs font-semibold text-white shadow-md transition-colors"
          >
            <i class="fa-solid fa-layer-group text-[10px]"></i>
            <span>Dettagli & Flussi</span>
          </a>
          <a
            href="${stremioHref}"
            class="w-full inline-flex items-center justify-center gap-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 px-3 py-1.5 text-xs font-semibold text-slate-200 transition-colors"
          >
            <i class="fa-solid fa-play text-[9px] text-indigo-400"></i>
            <span>Apri Stremio</span>
          </a>
          <button
            type="button"
            onclick="deleteMediaItem('${item.id}', '${item.title.replace(/'/g, "\\'")}')"
            class="w-full inline-flex items-center justify-center gap-1.5 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 text-rose-300 hover:text-rose-200 px-3 py-1 text-[11px] font-semibold transition-colors mt-1"
          >
            <i class="fa-solid fa-trash-can text-[10px]"></i>
            <span>Rimuovi</span>
          </button>
        </div>
      </div>

      <!-- Info Footer -->
      <div class="mt-2.5 px-1">
        <h4 class="text-xs font-bold text-white truncate group-hover:text-indigo-400 transition-colors" title="${item.title}">
          ${item.title}
        </h4>
        <div class="flex items-center justify-between text-[11px] text-slate-400 mt-1">
          <span>${item.year || "-"}</span>
          <span class="text-slate-500 text-[10px]">${timeAgo(item.last_accessed_at)}</span>
        </div>
      </div>

    </div>`;
}

function setFilterType(type) {
  currentFilterType = type;
  document.querySelectorAll(".library-filter-tab").forEach((btn) => {
    btn.className = "library-filter-tab px-3.5 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-white transition-all";
  });
  const activeBtn = document.getElementById(`filter-type-${type}`);
  if (activeBtn) {
    activeBtn.className = "library-filter-tab px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all bg-indigo-600 text-white shadow-sm";
  }
  loadLibrary();
}

function toggleCachedOnly(event) {
  cachedOnly = event.target.checked;
  loadLibrary();
}

function handleSearchInput(event) {
  searchQuery = event.target.value;
  filterAndRender();
}

async function deleteMediaItem(mediaId, title) {
  if (!confirm(`Sei sicuro di voler rimuovere "${title}" dalla tua libreria?\nI dati del titolo verranno eliminati, ma i file su disco non saranno toccati.`)) {
    return;
  }

  try {
    const res = await fetch(`/api/hub/library/${encodeURIComponent(mediaId)}`, {
      method: "DELETE",
      headers: { Accept: "application/json" },
    });
    if (!res.ok) throw new Error("Errore durante la cancellazione");

    // Remove from in-memory array and re-render
    allLibraryItems = allLibraryItems.filter((i) => i.id !== mediaId);
    filterAndRender();
  } catch (err) {
    alert("Errore durante la rimozione del titolo: " + err.message);
  }
}

// Initial load
document.addEventListener("DOMContentLoaded", () => {
  loadLibrary();
});
