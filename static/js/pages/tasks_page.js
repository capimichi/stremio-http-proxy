import { taskStatusBadgeHtml } from "../components/status_badge.js";
import { HubClient } from "../clients/hub_client.js";
import { timeAgo } from "../utils/formatters.js";

let currentStatusFilter = "";
let currentSearchQuery = "";
let allTasks = [];

function updateMetrics(tasks) {
  const total = tasks.length;
  const pending = tasks.filter((t) => t.status === "pending").length;
  const processing = tasks.filter((t) => t.status === "processing").length;
  const completed = tasks.filter((t) => t.status === "completed").length;

  const totalEl = document.getElementById("task-metric-total");
  if (totalEl) totalEl.textContent = total;

  const pendingEl = document.getElementById("task-metric-pending");
  if (pendingEl) pendingEl.textContent = pending;

  const processingEl = document.getElementById("task-metric-processing");
  if (processingEl) processingEl.textContent = processing;

  const completedEl = document.getElementById("task-metric-completed");
  if (completedEl) completedEl.textContent = completed;
}

function renderTasks(tasks) {
  const tbody = document.getElementById("tasks-full-table-body");
  if (!tbody) return;

  const query = currentSearchQuery.toLowerCase().trim();
  const filtered = tasks.filter((t) => {
    if (currentStatusFilter && t.status !== currentStatusFilter) {
      return false;
    }
    if (query) {
      const matchName = (t.display_name || t.name || "").toLowerCase().includes(query);
      const matchTitle = (t.media_title || "").toLowerCase().includes(query);
      const matchContentId = (t.content_id || "").toLowerCase().includes(query);
      const matchId = String(t.id).includes(query);
      const matchArgs = JSON.stringify(t.arguments || {}).toLowerCase().includes(query);
      return matchName || matchTitle || matchContentId || matchId || matchArgs;
    }
    return true;
  });

  if (filtered.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6" class="px-5 py-12 text-center text-slate-500">
          <div class="flex flex-col items-center justify-center gap-2">
            <i class="fa-solid fa-list-check text-slate-600 text-3xl mb-1"></i>
            <span class="font-semibold text-slate-300">Nessun task trovato</span>
            <span class="text-xs text-slate-500">Non ci sono job corrispondenti ai filtri o alla ricerca selezionata.</span>
          </div>
        </td>
      </tr>`;
    return;
  }

  tbody.innerHTML = filtered
    .map((t) => {
      let mediaHtml = `<span class="text-slate-500 font-mono text-[11px]">-</span>`;
      if (t.media_title) {
        let epBadge = "";
        if (t.season != null && t.episode != null) {
          epBadge = `<span class="px-1.5 py-0.5 rounded text-[10px] font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 shrink-0">S${t.season}E${t.episode}</span>`;
        }
        mediaHtml = `
          <div class="flex flex-col gap-0.5 max-w-xs">
            <div class="flex items-center gap-1.5 flex-wrap">
              <span class="font-semibold text-white text-xs truncate" title="${t.media_title}">${t.media_title}</span>
              ${epBadge}
            </div>
            ${t.content_id ? `<span class="text-[10px] text-slate-400 font-mono truncate" title="${t.content_id}">${t.content_id}</span>` : ""}
          </div>`;
      } else if (t.content_id) {
        mediaHtml = `<span class="font-mono text-[11px] text-slate-300 truncate max-w-xs block" title="${t.content_id}">${t.content_id}</span>`;
      } else if (t.arguments && Object.keys(t.arguments).length > 0) {
        mediaHtml = `<span class="font-mono text-[10px] text-slate-400 truncate max-w-xs block" title="${JSON.stringify(t.arguments)}">${JSON.stringify(t.arguments)}</span>`;
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
          timeHtml = `<span class="text-slate-400 text-[11px]">Pianificato (pronto)</span>`;
        }
      } else if (t.status === "processing") {
        timeHtml = `
          <div class="flex items-center gap-1 text-sky-400 font-mono text-[11px]">
            <i class="fa-solid fa-arrows-rotate text-[10px]"></i>
            <span>In esecuzione...</span>
          </div>`;
      } else {
        timeHtml = `<span class="text-slate-400 text-[11px]">${timeAgo(t.updated_at || t.created_at)}</span>`;
      }

      let detailsHtml = "";
      if (t.last_error) {
        detailsHtml = `
          <div class="flex flex-col items-end gap-0.5">
            <span class="text-rose-400 text-[10px] font-medium max-w-xs truncate" title="${t.last_error}">
              <i class="fa-solid fa-circle-exclamation mr-1"></i>${t.last_error}
            </span>
            <span class="text-slate-500 text-[10px]">Tentativo ${t.attempt}/${t.max_attempts}</span>
          </div>`;
      } else if (t.status === "pending" || t.status === "processing") {
        detailsHtml = `<span class="text-slate-400 text-[11px] font-mono">Tentativo ${t.attempt + (t.status === "processing" ? 0 : 1)} / ${t.max_attempts}</span>`;
      } else {
        detailsHtml = `<span class="text-emerald-400 text-[11px] font-medium flex items-center gap-1"><i class="fa-solid fa-circle-check text-[10px]"></i> Eseguito</span>`;
      }

      const workerHtml = t.claimed_by
        ? `<span class="font-mono text-[11px] text-slate-300 flex items-center gap-1"><i class="fa-solid fa-microchip text-[10px] text-indigo-400"></i> ${t.claimed_by}</span>`
        : `<span class="text-slate-500 font-mono text-[11px]">-</span>`;

      return `<tr class="hover:bg-slate-800/40 transition-colors">
        <td class="px-5 py-3.5 whitespace-nowrap">
          <div class="flex items-center gap-2.5">
            <span class="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-500/10 text-indigo-400 text-xs shrink-0 border border-indigo-500/20">
              <i class="fa-solid ${t.name === "fetch_next_episode" ? "fa-forward-step" : t.name === "optimize_media" ? "fa-wand-magic-sparkles" : t.name === "enrich_media_metadata" ? "fa-tags" : "fa-gear"}"></i>
            </span>
            <div class="flex flex-col">
              <span class="font-bold text-white text-xs">${t.display_name || t.name}</span>
              <span class="text-[10px] text-slate-400 font-mono">#${t.id} • ${t.name}</span>
            </div>
          </div>
        </td>
        <td class="px-5 py-3.5">${mediaHtml}</td>
        <td class="px-5 py-3.5 whitespace-nowrap">${taskStatusBadgeHtml(t.status)}</td>
        <td class="px-5 py-3.5 whitespace-nowrap">${timeHtml}</td>
        <td class="px-5 py-3.5 whitespace-nowrap">${workerHtml}</td>
        <td class="px-5 py-3.5 text-right whitespace-nowrap">${detailsHtml}</td>
      </tr>`;
    })
    .join("");
}

async function loadTasks() {
  try {
    const data = await HubClient.getTasks({ limit: 100 });
    allTasks = data.tasks || [];
    updateMetrics(allTasks);
    renderTasks(allTasks);
  } catch (err) {
    console.error("Errore caricamento task:", err);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  // Search input
  const searchInput = document.getElementById("task-search-input");
  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      currentSearchQuery = e.target.value;
      renderTasks(allTasks);
    });
  }

  // Filter tabs
  const tabButtons = document.querySelectorAll(".task-status-tab-btn");
  tabButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      tabButtons.forEach((b) => {
        b.className = "task-status-tab-btn px-3 py-1.5 rounded-lg font-semibold transition-colors bg-slate-800 text-slate-400 hover:text-white";
      });
      btn.className = "task-status-tab-btn px-3 py-1.5 rounded-lg font-semibold transition-colors bg-indigo-600 text-white";
      currentStatusFilter = btn.dataset.status || "";
      renderTasks(allTasks);
    });
  });

  loadTasks();
  setInterval(loadTasks, 2500);
});
