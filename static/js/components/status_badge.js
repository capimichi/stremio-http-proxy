/**
 * Status and Cache Badges
 */

export function statusBadgeHtml(status) {
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

export function taskStatusBadgeHtml(status) {
  switch (status) {
    case "completed":
      return `<span class="inline-flex items-center gap-1 rounded-md bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 text-[11px] font-semibold text-emerald-400">
        <i class="fa-solid fa-check text-[9px]"></i> Completato
      </span>`;
    case "processing":
      return `<span class="inline-flex items-center gap-1 rounded-md bg-sky-500/10 border border-sky-500/20 px-2 py-0.5 text-[11px] font-semibold text-sky-400 animate-pulse">
        <i class="fa-solid fa-arrows-rotate text-[9px]"></i> In esecuzione
      </span>`;
    case "pending":
      return `<span class="inline-flex items-center gap-1 rounded-md bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 text-[11px] font-semibold text-amber-400">
        <i class="fa-solid fa-clock text-[9px]"></i> In attesa
      </span>`;
    case "failed":
      return `<span class="inline-flex items-center gap-1 rounded-md bg-rose-500/10 border border-rose-500/20 px-2 py-0.5 text-[11px] font-semibold text-rose-400">
        <i class="fa-solid fa-xmark text-[9px]"></i> Fallito
      </span>`;
    default:
      return `<span class="inline-flex items-center gap-1 rounded-md bg-slate-800 border border-slate-700 px-2 py-0.5 text-[11px] font-medium text-slate-400">
        ${status || "-"}
      </span>`;
  }
}


export function cacheBadgeHtml(item) {
  const isSeries = item.type === "series";
  if (item.ready_streams_count > 0) {
    const countLabel = isSeries && item.cached_episodes_count > 0
      ? `${item.cached_episodes_count} ep pronti`
      : `${item.ready_streams_count} file pronto`;
    return `
      <span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 text-[10px] font-bold backdrop-blur">
        <i class="fa-solid fa-circle-check text-[9px]"></i>
        <span>${countLabel}</span>
      </span>`;
  } else if (item.is_downloading) {
    return `
      <span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-sky-500/20 text-sky-400 border border-sky-500/30 text-[10px] font-bold animate-pulse backdrop-blur">
        <i class="fa-solid fa-arrow-down text-[9px]"></i>
        <span>Download</span>
      </span>`;
  } else {
    return `
      <span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-slate-800/80 text-slate-400 border border-slate-700/60 text-[10px] font-medium backdrop-blur">
        Non in cache
      </span>`;
  }
}
