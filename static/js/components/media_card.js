import { PLACEHOLDER_POSTER, escapeHtml } from "../utils/dom.js";
import { timeAgo } from "../utils/formatters.js";
import { cacheBadgeHtml } from "./status_badge.js";

export class MediaCard {
  /**
   * Card for Personal Library Page
   */
  static renderLibrary(item) {
    const isSeries = item.type === "series";
    const typeBadge = isSeries ? "Serie TV" : "Film";
    const poster = item.poster || PLACEHOLDER_POSTER;
    const title = escapeHtml(item.title);
    const stremioHref = item.stremio_url || `stremio://detail/${item.type}/${item.id}`;

    return `
      <div class="group relative rounded-2xl bg-slate-900 border border-slate-800 hover:border-indigo-500/50 p-2.5 transition-all duration-200 hover:scale-[1.02] flex flex-col justify-between shadow-lg hover:shadow-indigo-500/10">
        
        <!-- Poster container -->
        <div class="relative w-full aspect-[2/3] rounded-xl overflow-hidden bg-slate-950 border border-slate-800/60 flex items-center justify-center">
          <div class="absolute inset-0 bg-slate-900 animate-pulse flex items-center justify-center text-slate-700 pointer-events-none">
            <i class="fa-solid fa-film text-xl"></i>
          </div>
          <img
            src="${poster}"
            alt="${title}"
            class="w-full h-full object-cover group-hover:opacity-95 transition-opacity relative z-10"
            loading="lazy"
            onload="this.previousElementSibling && this.previousElementSibling.remove()"
            onerror="this.src='${PLACEHOLDER_POSTER}'; this.previousElementSibling && this.previousElementSibling.remove()"
          >

          <!-- Top Badges -->
          <div class="absolute top-2 left-2 flex flex-col gap-1 items-start pointer-events-none">
            <span class="px-2 py-0.5 rounded bg-black/80 backdrop-blur text-[10px] font-bold text-slate-200 shadow">
              ${typeBadge}
            </span>
          </div>

          <div class="absolute top-2 right-2 pointer-events-none">
            ${cacheBadgeHtml(item)}
          </div>

          <!-- Hover Quick Actions Overlay -->
          <div class="absolute inset-0 bg-slate-950/80 backdrop-blur-sm opacity-0 group-hover:opacity-100 transition-opacity flex flex-col items-center justify-center gap-2 p-3 text-center">
            <a
              href="/dashboard/browser/${item.type}/${item.id}"
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
              data-action="delete"
              data-id="${item.id}"
              data-title="${title}"
              class="w-full inline-flex items-center justify-center gap-1.5 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 text-rose-300 hover:text-rose-200 px-3 py-1 text-[11px] font-semibold transition-colors mt-1"
            >
              <i class="fa-solid fa-trash-can text-[10px]"></i>
              <span>Rimuovi</span>
            </button>
          </div>
        </div>

        <!-- Info Footer -->
        <div class="mt-2.5 px-1">
          <h4 class="text-xs font-bold text-white truncate group-hover:text-indigo-400 transition-colors" title="${title}">
            ${title}
          </h4>
          <div class="flex items-center justify-between text-[11px] text-slate-400 mt-1">
            <span>${item.year || "-"}</span>
            <span class="text-slate-500 text-[10px]">${timeAgo(item.last_accessed_at)}</span>
          </div>
        </div>

      </div>`;
  }

  /**
   * Card for Recent Media Grid in Home
   */
  static renderRecent(item) {
    const isSeries = item.content_type === "series" || item.season !== null;
    const epBadge = isSeries && item.season !== null && item.episode !== null ? `S${item.season} E${item.episode}` : (isSeries ? "Serie" : "Film");
    const poster = item.poster || PLACEHOLDER_POSTER;
    const displayTitle = escapeHtml(item.clean_title || item.title);

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
        <div class="relative w-full aspect-[2/3] rounded-lg overflow-hidden bg-slate-950 flex items-center justify-center">
          <div class="absolute inset-0 bg-slate-900 animate-pulse flex items-center justify-center text-slate-700 pointer-events-none">
            <i class="fa-solid fa-film text-lg"></i>
          </div>
          <img src="${poster}" alt="${displayTitle}" class="w-full h-full object-cover group-hover:opacity-90 transition-opacity relative z-10" loading="lazy" onload="this.previousElementSibling && this.previousElementSibling.remove()" onerror="this.src='${PLACEHOLDER_POSTER}'; this.previousElementSibling && this.previousElementSibling.remove()">
          
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
            <span>${escapeHtml(item.subtitle || (item.episode_label || (isSeries ? "Serie" : "Film")))}</span>
            <span class="text-slate-500">${timeAgo(item.played_at)}</span>
          </div>
        </div>
      </a>`;
  }
}
