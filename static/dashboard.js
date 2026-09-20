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
  return new Date(value * 1000).toLocaleString("it-IT", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function timeAgo(timestamp) {
  if (!timestamp) return "";
  const seconds = Math.floor(Date.now() / 1000 - timestamp);
  if (seconds < 60) return "Poco fa";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min fa`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} ore fa`;
  const days = Math.floor(hours / 24);
  return `${days} giorni fa`;
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
        Non in cache
      </span>`;
  }
}

// Update Topbar and Widget Summaries
function updateSummary(payload) {
  const cacheSizeFormatted = formatBytes(payload.total_cache_bytes);

  // Header pills
  const headerCache = document.getElementById("header-cache-size");
  if (headerCache) headerCache.textContent = cacheSizeFormatted;

  const headerActive = document.getElementById("header-active-count");
  if (headerActive) headerActive.textContent = `${payload.active_downloads} in download`;

  // Storage Widget
  const widgetCache = document.getElementById("widget-cache-size");
  if (widgetCache) widgetCache.textContent = cacheSizeFormatted;

  const widgetActive = document.getElementById("widget-active-downloads");
  if (widgetActive) widgetActive.textContent = payload.active_downloads;

  const counts = payload.status_counts || {};
  const ready = counts.ready || 0;
  const widgetReady = document.getElementById("widget-ready-count");
  if (widgetReady) widgetReady.textContent = ready;

  // Assume max cache default ~20GB or calculate percentage
  const maxStorageBytes = 20 * 1024 * 1024 * 1024;
  const storagePct = Math.min(100, Math.round((payload.total_cache_bytes / maxStorageBytes) * 100));
  const storageBar = document.getElementById("widget-storage-bar");
  if (storageBar) storageBar.style.width = `${Math.max(4, storagePct)}%`;

  // Install Stremio link in header
  if (payload.manifest_url) {
    const installBtn = document.getElementById("header-stremio-install");
    if (installBtn) {
      installBtn.href = payload.manifest_url.replace(/^http/, "stremio");
    }
  }
}

// Render Active Downloads Table
function renderActiveDownloadsTable(items, isActive) {
  const tbody = document.getElementById("active-downloads-body");
  const badge = document.getElementById("active-downloads-badge");
  const titleEl = document.getElementById("active-downloads-title");
  if (!tbody) return;

  if (titleEl) {
    titleEl.textContent = isActive ? "Download in Corso nella Cache" : "Ultimi download completati";
  }

  if (badge) {
    badge.textContent = isActive ? items.length : "0";
    if (isActive && items.length > 0) {
      badge.className = "inline-flex items-center rounded-full bg-sky-500/20 border border-sky-500/40 px-2 py-0.5 text-[11px] font-bold text-sky-300 animate-pulse";
    } else {
      badge.className = "inline-flex items-center rounded-full bg-slate-800 border border-slate-700 px-2 py-0.5 text-[11px] font-medium text-slate-400";
    }
  }

  if (!items || items.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="5" class="px-5 py-8 text-center text-slate-500">
          <div class="flex flex-col items-center justify-center gap-1.5">
            <i class="fa-solid fa-circle-check text-emerald-500 text-2xl mb-1"></i>
            <span class="font-medium text-slate-300">Nessun download attivo al momento.</span>
            <span class="text-xs text-slate-500">Tutti i contenuti accodati sono pronti in cache locale.</span>
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

    return `<tr class="hover:bg-slate-800/40 transition-colors">
      <td class="px-5 py-3 text-sm font-medium text-slate-200 max-w-xs truncate" title="${title}">
        ${title}
      </td>
      <td class="px-5 py-3 text-slate-400 whitespace-nowrap font-mono text-xs">${size}</td>
      <td class="px-5 py-3 whitespace-nowrap">${statusBadgeHtml(d.status)}</td>
      <td class="px-5 py-3 text-slate-400 whitespace-nowrap">
        <div class="flex flex-col gap-1">
          <div class="flex items-center gap-2">
            <div class="w-24 sm:w-32 h-1.5 rounded-full bg-slate-800 overflow-hidden">
              <div class="h-full rounded-full ${d.status === "ready" ? "bg-emerald-500" : "bg-gradient-to-r from-indigo-500 to-sky-400"}" style="width: ${pct}%"></div>
            </div>
            <span class="font-mono text-xs font-semibold text-slate-300">${formatProgress(d.progress_percent)}</span>
          </div>
          ${speed ? `<span class="text-[11px] text-sky-400 font-mono"><i class="fa-solid fa-arrow-down mr-1"></i>${speed}</span>` : ""}
        </div>
      </td>
      <td class="px-5 py-3 text-right whitespace-nowrap">
        <a href="/dashboard/cache-entry/${d.infohash}/${d.index}" class="inline-flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-800 hover:bg-slate-700 px-2.5 py-1 text-xs font-medium text-slate-300 transition-colors">
          Dettagli
        </a>
      </td>
    </tr>`;
  }).join("");
}

// Render Hero Card for Latest Played Media
function renderHeroNowPlaying(item) {
  const loadingEl = document.getElementById("hero-loading");
  const contentEl = document.getElementById("hero-content");
  const emptyEl = document.getElementById("hero-empty");

  if (loadingEl) loadingEl.classList.add("hidden");

  if (!item) {
    if (contentEl) contentEl.classList.add("hidden");
    if (emptyEl) emptyEl.classList.remove("hidden");
    return;
  }

  if (emptyEl) emptyEl.classList.add("hidden");
  if (contentEl) contentEl.classList.remove("hidden");

  const placeholderSvg = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 150 220'%3E%3Crect fill='%231e293b' width='150' height='220'/%3E%3Ctext x='50%25' y='50%25' dominant-baseline='middle' text-anchor='middle' fill='%2364748b' font-family='sans-serif' font-size='12'%3ENo Poster%3C/text%3E%3C/svg%3E";

  // Poster
  const posterImg = document.getElementById("hero-poster");
  if (posterImg) {
    posterImg.onerror = function() {
      this.src = placeholderSvg;
    };
    posterImg.src = item.poster || placeholderSvg;
  }

  // Media Badge (Serie / Film)
  const mediaBadge = document.getElementById("hero-media-badge");
  if (mediaBadge) {
    mediaBadge.textContent = item.content_type === "movie" ? "Film" : "Serie TV";
  }

  // Played time
  const playedTime = document.getElementById("hero-played-time");
  if (playedTime) {
    playedTime.textContent = `Iniziato ${timeAgo(item.played_at)}`;
  }

  // Title & Subtitle
  const titleEl = document.getElementById("hero-title");
  if (titleEl) {
    titleEl.textContent = item.clean_title || item.show_title || item.title;
  }

  const subtitleEl = document.getElementById("hero-subtitle");
  if (subtitleEl) {
    if (item.season !== null && item.episode !== null) {
      subtitleEl.textContent = `Stagione ${item.season} • Episodio ${item.episode}`;
    } else {
      subtitleEl.textContent = item.subtitle || (item.content_type === "movie" ? "Film" : "Serie TV");
    }
  }

  // Streams count badge
  const streamsBadge = document.getElementById("hero-streams-count-badge");
  if (streamsBadge) {
    if (item.streams_count > 1) {
      streamsBadge.textContent = `${item.streams_count} stream disponibili`;
      streamsBadge.classList.remove("hidden");
    } else {
      streamsBadge.classList.add("hidden");
    }
  }

  // Status Box Styling & Information
  const iconBox = document.getElementById("hero-status-icon-box");
  const statusText = document.getElementById("hero-status-text");
  const statusSubtext = document.getElementById("hero-status-subtext");
  const statusMetric = document.getElementById("hero-status-metric");
  const progressContainer = document.getElementById("hero-progress-container");
  const progressBar = document.getElementById("hero-progress-bar");

  if (item.status === "ready") {
    iconBox.className = "flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-sm";
    iconBox.innerHTML = '<i class="fa-solid fa-circle-check"></i>';
    statusText.textContent = "Pronto in Cache Locale";
    statusSubtext.textContent = "File già scaricato sul server. Avvio istantaneo e fluido in Stremio.";
    const activeStream = item.active_stream || (item.streams && item.streams[0]);
    statusMetric.textContent = activeStream && activeStream.size_bytes ? formatBytes(activeStream.size_bytes) : "Pronto";
    progressContainer.classList.add("hidden");
  } else if (item.status === "downloading") {
    iconBox.className = "flex h-8 w-8 items-center justify-center rounded-lg bg-sky-500/10 text-sky-400 border border-sky-500/20 text-sm animate-pulse";
    iconBox.innerHTML = '<i class="fa-solid fa-arrow-down"></i>';
    const active = item.active_stream || {};
    const pct = active.progress_percent !== null && active.progress_percent !== undefined ? Math.round(active.progress_percent) : 0;
    const speed = formatSpeed(active.speed_bps);
    statusText.textContent = `In Download nella Cache (${pct}%)`;
    statusSubtext.textContent = speed ? `Download in corso a ${speed}. Riproduzione via TorrServer.` : "Scaricamento in corso...";
    statusMetric.textContent = speed || `${pct}%`;
    progressContainer.classList.remove("hidden");
    if (progressBar) progressBar.style.width = `${pct}%`;
  } else if (item.status === "queued") {
    iconBox.className = "flex h-8 w-8 items-center justify-center rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/20 text-sm";
    iconBox.innerHTML = '<i class="fa-solid fa-clock"></i>';
    statusText.textContent = "In Coda di Download";
    statusSubtext.textContent = "Il download in cache inizierà non appena il worker completerà i job prioritari.";
    statusMetric.textContent = "In Coda";
    progressContainer.classList.add("hidden");
  } else {
    iconBox.className = "flex h-8 w-8 items-center justify-center rounded-lg bg-slate-800 text-slate-400 border border-slate-700 text-sm";
    iconBox.innerHTML = '<i class="fa-solid fa-network-wired"></i>';
    statusText.textContent = "Riproduzione Diretta (Non in cache)";
    statusSubtext.textContent = "Il contenuto è stato trasmesso senza essere salvato in cache locale.";
    statusMetric.textContent = "Esterno";
    progressContainer.classList.add("hidden");
  }

  // Buttons
  const stremioBtn = document.getElementById("hero-stremio-btn");
  if (stremioBtn) stremioBtn.href = item.stremio_url || "#";

  const detailBtn = document.getElementById("hero-detail-btn");
  if (detailBtn) {
    detailBtn.href = `/dashboard/browser/${item.content_type}/${item.imdb_id}`;
  }
}

// Render Recent Media Grid
function renderRecentMediaGrid(items) {
  const container = document.getElementById("recent-media-grid");
  if (!container) return;

  if (!items || items.length === 0) {
    container.innerHTML = `
      <div class="col-span-full py-8 text-center text-slate-500 text-sm">
        Nessun titolo riprodotto di recente.
      </div>`;
    return;
  }

  const placeholderSvg = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 150 220'%3E%3Crect fill='%231e293b' width='150' height='220'/%3E%3Ctext x='50%25' y='50%25' dominant-baseline='middle' text-anchor='middle' fill='%2364748b' font-family='sans-serif' font-size='12'%3ENo Poster%3C/text%3E%3C/svg%3E";

  container.innerHTML = items.map((item) => {
    const isSeries = item.content_type === "series" || item.season !== null;
    const epBadge = isSeries && item.season !== null && item.episode !== null ? `S${item.season} E${item.episode}` : (isSeries ? "Serie" : "Film");
    const poster = item.poster || placeholderSvg;
    const displayTitle = item.clean_title || item.title;
    
    // Status dot color
    let statusDot = `<span class="h-2 w-2 rounded-full bg-slate-500"></span>`;
    if (item.status === "ready") {
      statusDot = `<span class="h-2 w-2 rounded-full bg-emerald-400 shadow-sm shadow-emerald-400"></span>`;
    } else if (item.status === "downloading") {
      statusDot = `<span class="h-2 w-2 rounded-full bg-sky-400 animate-ping"></span>`;
    } else if (item.status === "queued") {
      statusDot = `<span class="h-2 w-2 rounded-full bg-amber-400"></span>`;
    }

    return `
      <a href="/dashboard/browser/${item.content_type}/${item.imdb_id}" class="group relative rounded-xl bg-slate-900 border border-slate-800 hover:border-indigo-500/50 p-2 transition-all hover:scale-[1.02] flex flex-col justify-between shadow-md">
        <!-- Poster container -->
        <div class="relative w-full aspect-[2/3] rounded-lg overflow-hidden bg-slate-800">
          <img src="${poster}" alt="${displayTitle}" class="w-full h-full object-cover group-hover:opacity-90 transition-opacity" loading="lazy" onerror="this.src='${placeholderSvg}'">
          
          <!-- Top Badges -->
          <div class="absolute top-1.5 left-1.5 px-1.5 py-0.5 rounded bg-black/75 backdrop-blur text-[10px] font-bold text-slate-200">
            ${epBadge}
          </div>

          <div class="absolute top-1.5 right-1.5 flex items-center gap-1 px-1.5 py-0.5 rounded bg-black/75 backdrop-blur text-[10px] font-semibold text-slate-300">
            ${statusDot}
            <span class="capitalize text-[9px]">${item.status === "ready" ? "In Cache" : (item.status === "downloading" ? "Download" : "")}</span>
          </div>
        </div>

        <!-- Info -->
        <div class="mt-2 px-1">
          <p class="text-xs font-semibold text-white truncate group-hover:text-indigo-400 transition-colors" title="${displayTitle}">
            ${displayTitle}
          </p>
          <div class="flex items-center justify-between text-[10px] text-slate-400 mt-0.5">
            <span>${item.subtitle || (item.episode_label || (isSeries ? "Serie" : "Film"))}</span>
            <span class="text-slate-500">${timeAgo(item.played_at)}</span>
          </div>
        </div>
      </a>`;
  }).join("");
}

// Fetch Hub Data
async function refreshHubData() {
  try {
    const res = await fetch("/api/hub/recent?limit=12", {
      headers: { Accept: "application/json" },
    });
    if (res.ok) {
      const data = await res.json();
      const items = data.items || [];
      renderHeroNowPlaying(items[0] || null);
      renderRecentMediaGrid(items);
    }
  } catch (err) {
    console.error("Errore fetch hub recent:", err);
  }
}

// Fetch Downloads Queue
async function refreshDownloadsQueue() {
  try {
    const res = await fetch("/downloads?page=1&limit=5", {
      headers: { Accept: "application/json" },
    });
    if (res.ok) {
      const payload = await res.json();
      updateSummary(payload);

      if (payload.active_items && payload.active_items.length > 0) {
        renderActiveDownloadsTable(payload.active_items, true);
      } else {
        renderActiveDownloadsTable(payload.downloads, false);
      }
    }
  } catch (err) {
    console.error("Errore aggiornamento downloads:", err);
  }
}

// Initial loads
refreshHubData();
refreshDownloadsQueue();

// Polling intervals
setInterval(refreshDownloadsQueue, 3000);
setInterval(refreshHubData, 6000);
