import { MediaCard } from "../components/media_card.js";
import { statusBadgeHtml, taskStatusBadgeHtml } from "../components/status_badge.js";
import { HubService } from "../services/hub_service.js";
import { PLACEHOLDER_POSTER } from "../utils/dom.js";
import { formatBytes, formatProgress, formatSpeed, timeAgo } from "../utils/formatters.js";

const hubService = new HubService();

// Update Topbar and Widget Summaries
function updateSummary(payload) {
  if (!payload) return;
  const cacheSizeFormatted = formatBytes(payload.total_cache_bytes);

  const headerCache = document.getElementById("header-cache-size");
  if (headerCache) headerCache.textContent = cacheSizeFormatted;

  const headerActive = document.getElementById("header-active-count");
  if (headerActive) headerActive.textContent = `${payload.active_downloads || 0} in download`;

  const widgetCache = document.getElementById("widget-cache-size");
  if (widgetCache) widgetCache.textContent = cacheSizeFormatted;

  const widgetActive = document.getElementById("widget-active-downloads");
  if (widgetActive) widgetActive.textContent = payload.active_downloads || 0;

  const counts = payload.status_counts || {};
  const ready = counts.ready || 0;
  const widgetReady = document.getElementById("widget-ready-count");
  if (widgetReady) widgetReady.textContent = ready;

  const maxStorageBytes = 20 * 1024 * 1024 * 1024;
  const storagePct = Math.min(100, Math.round(((payload.total_cache_bytes || 0) / maxStorageBytes) * 100));
  const storageBar = document.getElementById("widget-storage-bar");
  if (storageBar) storageBar.style.width = `${Math.max(4, storagePct)}%`;

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

  tbody.innerHTML = items
    .map((d) => {
      const rawTitle = d.title || d.cache_key;
      const size =
        d.status === "ready"
          ? formatBytes(d.downloaded_bytes)
          : d.expected_bytes
          ? `${formatBytes(d.downloaded_bytes)} / ${formatBytes(d.expected_bytes)}`
          : formatBytes(d.downloaded_bytes);
      const speed = formatSpeed(d.download_speed_bytes_per_second);
      const pct = Math.max(0, Math.min(d.progress_percent ?? 0, 100));

      let titleHtml = "";
      if (d.media_title) {
        let epBadge = "";
        if (d.season != null && d.episode != null) {
          epBadge = `<span class="px-1.5 py-0.5 rounded text-[10px] font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 shrink-0">S${d.season}E${d.episode}</span>`;
        }
        titleHtml = `
          <div class="flex flex-col min-w-0 max-w-xs">
            <div class="flex items-center gap-1.5 flex-wrap">
              <span class="font-semibold text-white text-xs truncate" title="${d.media_title}">${d.media_title}</span>
              ${epBadge}
            </div>
            ${d.episode_title ? `<span class="text-[11px] text-slate-300 truncate" title="${d.episode_title}">${d.episode_title}</span>` : ""}
            <span class="text-[10px] text-slate-500 font-mono truncate" title="${rawTitle}">${rawTitle}</span>
          </div>
        `;
      } else if (d.season != null && d.episode != null) {
        titleHtml = `
          <div class="flex flex-col min-w-0 max-w-xs">
            <div class="flex items-center gap-1.5 flex-wrap">
              <span class="px-1.5 py-0.5 rounded text-[10px] font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 shrink-0">S${d.season}E${d.episode}</span>
              <span class="font-semibold text-white text-xs truncate" title="${rawTitle}">${rawTitle}</span>
            </div>
          </div>
        `;
      } else {
        titleHtml = `<span class="text-sm font-medium text-slate-200 max-w-xs truncate block" title="${rawTitle}">${rawTitle}</span>`;
      }

      return `<tr class="hover:bg-slate-800/40 transition-colors">
        <td class="px-5 py-3">
          ${titleHtml}
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
    })
    .join("");
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

  const posterImg = document.getElementById("hero-poster");
  const posterSkeleton = document.getElementById("hero-poster-skeleton");
  if (posterImg) {
    posterImg.onload = function () {
      this.classList.remove("opacity-0");
      if (posterSkeleton) posterSkeleton.classList.add("hidden");
    };
    posterImg.onerror = function () {
      this.src = PLACEHOLDER_POSTER;
      this.classList.remove("opacity-0");
      if (posterSkeleton) posterSkeleton.classList.add("hidden");
    };
    posterImg.src = item.poster || PLACEHOLDER_POSTER;
    if (posterImg.complete && posterImg.naturalWidth > 0) {
      posterImg.classList.remove("opacity-0");
      if (posterSkeleton) posterSkeleton.classList.add("hidden");
    }
  }

  const mediaBadge = document.getElementById("hero-media-badge");
  if (mediaBadge) {
    mediaBadge.textContent = item.content_type === "movie" ? "Film" : "Serie TV";
  }

  const playedTime = document.getElementById("hero-played-time");
  if (playedTime) {
    playedTime.textContent = `Iniziato ${timeAgo(item.played_at)}`;
  }

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

  const streamsBadge = document.getElementById("hero-streams-count-badge");
  if (streamsBadge) {
    if (item.streams_count > 1) {
      streamsBadge.textContent = `${item.streams_count} stream disponibili`;
      streamsBadge.classList.remove("hidden");
    } else {
      streamsBadge.classList.add("hidden");
    }
  }

  const iconBox = document.getElementById("hero-status-icon-box");
  const statusText = document.getElementById("hero-status-text");
  const statusSubtext = document.getElementById("hero-status-subtext");
  const statusMetric = document.getElementById("hero-status-metric");
  const progressContainer = document.getElementById("hero-progress-container");
  const progressBar = document.getElementById("hero-progress-bar");

  if (item.status === "ready") {
    if (iconBox) {
      iconBox.className = "flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-sm";
      iconBox.innerHTML = '<i class="fa-solid fa-circle-check"></i>';
    }
    if (statusText) statusText.textContent = "Pronto in Cache Locale";
    if (statusSubtext) statusSubtext.textContent = "File già scaricato sul server. Avvio istantaneo e fluido in Stremio.";
    const activeStream = item.active_stream || (item.streams && item.streams[0]);
    if (statusMetric) statusMetric.textContent = activeStream && activeStream.size_bytes ? formatBytes(activeStream.size_bytes) : "Pronto";
    if (progressContainer) progressContainer.classList.add("hidden");
  } else if (item.status === "downloading") {
    if (iconBox) {
      iconBox.className = "flex h-8 w-8 items-center justify-center rounded-lg bg-sky-500/10 text-sky-400 border border-sky-500/20 text-sm animate-pulse";
      iconBox.innerHTML = '<i class="fa-solid fa-arrow-down"></i>';
    }
    const active = item.active_stream || {};
    const pct = active.progress_percent !== null && active.progress_percent !== undefined ? Math.round(active.progress_percent) : 0;
    const speed = formatSpeed(active.speed_bps);
    if (statusText) statusText.textContent = `In Download nella Cache (${pct}%)`;
    if (statusSubtext) statusSubtext.textContent = speed ? `Download in corso a ${speed}. Riproduzione via TorrServer.` : "Scaricamento in corso...";
    if (statusMetric) statusMetric.textContent = speed || `${pct}%`;
    if (progressContainer) progressContainer.classList.remove("hidden");
    if (progressBar) progressBar.style.width = `${pct}%`;
  } else if (item.status === "queued") {
    if (iconBox) {
      iconBox.className = "flex h-8 w-8 items-center justify-center rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/20 text-sm";
      iconBox.innerHTML = '<i class="fa-solid fa-clock"></i>';
    }
    if (statusText) statusText.textContent = "In Coda di Download";
    if (statusSubtext) statusSubtext.textContent = "Il download in cache inizierà non appena il worker completerà i job prioritari.";
    if (statusMetric) statusMetric.textContent = "In Coda";
    if (progressContainer) progressContainer.classList.add("hidden");
  } else {
    if (iconBox) {
      iconBox.className = "flex h-8 w-8 items-center justify-center rounded-lg bg-slate-800 text-slate-400 border border-slate-700 text-sm";
      iconBox.innerHTML = '<i class="fa-solid fa-network-wired"></i>';
    }
    if (statusText) statusText.textContent = "Riproduzione Diretta (Non in cache)";
    if (statusSubtext) statusSubtext.textContent = "Il contenuto è stato trasmesso senza essere salvato in cache locale.";
    if (statusMetric) statusMetric.textContent = "Esterno";
    if (progressContainer) progressContainer.classList.add("hidden");
  }

  const stremioBtn = document.getElementById("hero-stremio-btn");
  if (stremioBtn && item.stremio_url) {
    stremioBtn.href = item.stremio_url;
  }

  const detailBtn = document.getElementById("hero-detail-btn");
  if (detailBtn) {
    detailBtn.href = `/dashboard/browser/${item.content_type}/${item.imdb_id}`;
  }
}

// Render Recent Grid
function renderRecentMediaGrid(items) {
  const container = document.getElementById("recent-media-grid");
  if (!container) return;

  if (!items || items.length === 0) {
    container.innerHTML = `
      <div class="col-span-full py-8 text-center text-xs text-slate-500">
        Nessun titolo riprodotto di recente.
      </div>`;
    return;
  }

  container.innerHTML = items.map((item) => MediaCard.renderRecent(item)).join("");
}

// Render Tasks Table
function renderTasksTable(tasks) {
  const tbody = document.getElementById("tasks-table-body");
  const badge = document.getElementById("tasks-badge");
  if (!tbody) return;

  const activeCount = (tasks || []).filter((t) => t.status === "pending" || t.status === "processing").length;
  if (badge) {
    badge.textContent = tasks ? tasks.length : "0";
    if (activeCount > 0) {
      badge.className = "inline-flex items-center rounded-full bg-indigo-500/20 border border-indigo-500/40 px-2 py-0.5 text-[11px] font-bold text-indigo-300 animate-pulse";
    } else {
      badge.className = "inline-flex items-center rounded-full bg-slate-800 border border-slate-700 px-2 py-0.5 text-[11px] font-medium text-slate-400";
    }
  }

  if (!tasks || tasks.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="5" class="px-5 py-8 text-center text-slate-500">
          <div class="flex flex-col items-center justify-center gap-1.5">
            <i class="fa-solid fa-check-double text-indigo-400 text-2xl mb-1"></i>
            <span class="font-medium text-slate-300">Nessun task asincrono in coda.</span>
            <span class="text-xs text-slate-500">I task di prefetch, arricchimento metadati e ottimizzazione compariranno qui.</span>
          </div>
        </td>
      </tr>`;
    return;
  }

  tbody.innerHTML = tasks
    .map((t) => {
      let mediaHtml = "-";
      if (t.media_title) {
        let epBadge = "";
        if (t.season != null && t.episode != null) {
          epBadge = `<span class="px-1.5 py-0.5 rounded text-[10px] font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 shrink-0">S${t.season}E${t.episode}</span>`;
        }
        mediaHtml = `
          <div class="flex items-center gap-1.5 flex-wrap">
            <span class="font-semibold text-white text-xs truncate max-w-[200px]" title="${t.media_title}">${t.media_title}</span>
            ${epBadge}
          </div>`;
      } else if (t.content_id) {
        mediaHtml = `<span class="font-mono text-[11px] text-slate-300 truncate max-w-[200px] block" title="${t.content_id}">${t.content_id}</span>`;
      }

      let timeHtml = "";
      if (t.status === "pending") {
        if (t.remaining_seconds > 0) {
          const mins = Math.floor(t.remaining_seconds / 60);
          const secs = t.remaining_seconds % 60;
          const timeStr = mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
          timeHtml = `
            <div class="flex items-center gap-1 text-amber-400 font-mono text-[11px]">
              <i class="fa-solid fa-hourglass-half text-[10px] animate-pulse"></i>
              <span>Tra ${timeStr}</span>
            </div>`;
        } else {
          timeHtml = `<span class="text-slate-400 text-[11px]">Pronto per esecuzione</span>`;
        }
      } else if (t.status === "processing") {
        timeHtml = `
          <div class="flex items-center gap-1 text-sky-400 font-mono text-[11px]">
            <i class="fa-solid fa-arrows-rotate text-[10px] animate-spin"></i>
            <span>In esecuzione...</span>
          </div>`;
      } else {
        timeHtml = `<span class="text-slate-400 text-[11px]">${timeAgo(t.updated_at || t.created_at)}</span>`;
      }

      let detailsHtml = "";
      if (t.last_error) {
        detailsHtml = `<span class="text-rose-400 text-[10px] max-w-xs truncate block" title="${t.last_error}"><i class="fa-solid fa-circle-exclamation mr-1"></i>${t.last_error}</span>`;
      } else if (t.status === "pending" || t.status === "processing") {
        detailsHtml = `<span class="text-slate-500 text-[10px]">Tentativo ${t.attempt + (t.status === "processing" ? 0 : 1)}/${t.max_attempts}</span>`;
      } else {
        detailsHtml = `<span class="text-slate-500 text-[10px]">Completato con successo</span>`;
      }

      return `<tr class="hover:bg-slate-800/40 transition-colors">
        <td class="px-5 py-3 whitespace-nowrap">
          <div class="flex items-center gap-2">
            <span class="flex h-6 w-6 items-center justify-center rounded bg-indigo-500/10 text-indigo-400 text-xs">
              <i class="fa-solid ${t.name === "fetch_next_episode" ? "fa-forward-step" : t.name === "optimize_media" ? "fa-wand-magic-sparkles" : "fa-gear"}"></i>
            </span>
            <div class="flex flex-col">
              <span class="font-semibold text-white text-xs">${t.display_name || t.name}</span>
              <span class="text-[10px] text-slate-500 font-mono">#${t.id} • ${t.name}</span>
            </div>
          </div>
        </td>
        <td class="px-5 py-3 whitespace-nowrap">${mediaHtml}</td>
        <td class="px-5 py-3 whitespace-nowrap">${taskStatusBadgeHtml(t.status)}</td>
        <td class="px-5 py-3 whitespace-nowrap">${timeHtml}</td>
        <td class="px-5 py-3 text-right whitespace-nowrap">${detailsHtml}</td>
      </tr>`;
    })
    .join("");
}

// Main Polling Loop
async function tick() {
  try {
    const [recentItems, downloads, tasks] = await Promise.all([
      hubService.fetchRecent(12),
      hubService.fetchDownloads(1, 5),
      hubService.fetchTasks(10),
    ]);

    renderHeroNowPlaying(recentItems[0] || null);
    renderRecentMediaGrid(recentItems);

    updateSummary(downloads);
    if (downloads && downloads.active_items && downloads.active_items.length > 0) {
      renderActiveDownloadsTable(downloads.active_items, true);
    } else if (downloads) {
      renderActiveDownloadsTable(downloads.downloads || [], false);
    }

    renderTasksTable(tasks);
  } catch (err) {
    console.error("Errore polling dashboard:", err);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  tick();
  setInterval(tick, 2500);
});

