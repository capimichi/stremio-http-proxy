import { MediaCard } from "../components/media_card.js";
import { showToast } from "../components/toast.js";
import { LibraryService } from "../services/library_service.js";
import { debounce } from "../utils/dom.js";

const libraryService = new LibraryService();

async function refreshLibrary() {
  const loadingEl = document.getElementById("library-loading");
  const gridEl = document.getElementById("library-grid");
  const emptyEl = document.getElementById("library-empty");
  const totalBadge = document.getElementById("library-total-badge");

  try {
    const { items, total } = await libraryService.fetchLibrary();
    if (totalBadge) {
      totalBadge.textContent = `${total} titoli`;
    }
    if (loadingEl) loadingEl.classList.add("hidden");
    render();
  } catch (err) {
    if (loadingEl) loadingEl.classList.add("hidden");
    if (gridEl) gridEl.classList.add("hidden");
    if (emptyEl) {
      emptyEl.classList.remove("hidden");
      document.getElementById("empty-title").textContent = "Impossibile caricare la libreria";
      document.getElementById("empty-subtext").textContent = err.message || "Errore di connessione.";
    }
    showToast("Errore nel caricamento della libreria", "error");
  }
}

function render() {
  const gridEl = document.getElementById("library-grid");
  const emptyEl = document.getElementById("library-empty");
  const filtered = libraryService.getFilteredItems();

  if (filtered.length === 0) {
    if (gridEl) gridEl.classList.add("hidden");
    if (emptyEl) {
      emptyEl.classList.remove("hidden");
      if (libraryService.searchQuery.trim() || libraryService.cachedOnly || libraryService.filterType !== "all") {
        document.getElementById("empty-title").textContent = "Nessun risultato con i filtri attuali";
        document.getElementById("empty-subtext").textContent = "Prova a modificare i termini di ricerca o a disattivare i filtri.";
      } else {
        document.getElementById("empty-title").textContent = "La tua libreria è vuota";
        document.getElementById("empty-subtext").textContent = "I titoli vengono aggiunti automaticamente qui quando riproduci uno stream o consulti contenuti.";
      }
    }
    return;
  }

  if (emptyEl) emptyEl.classList.add("hidden");
  if (gridEl) {
    gridEl.classList.remove("hidden");
    gridEl.innerHTML = filtered.map((item) => MediaCard.renderLibrary(item)).join("");
  }
}

// Event handlers
function setupEvents() {
  // Filter tabs
  const tabAll = document.getElementById("filter-type-all");
  const tabSeries = document.getElementById("filter-type-series");
  const tabMovie = document.getElementById("filter-type-movie");

  const tabs = [
    { el: tabAll, type: "all" },
    { el: tabSeries, type: "series" },
    { el: tabMovie, type: "movie" },
  ];

  tabs.forEach(({ el, type }) => {
    if (!el) return;
    el.addEventListener("click", () => {
      tabs.forEach((t) => {
        if (t.el) t.el.className = "library-filter-tab px-3.5 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-white transition-all";
      });
      el.className = "library-filter-tab px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all bg-indigo-600 text-white shadow-sm";
      libraryService.setFilterType(type);
      refreshLibrary();
    });
  });

  // Cached only toggle
  const cachedToggle = document.getElementById("filter-cached-only");
  if (cachedToggle) {
    cachedToggle.addEventListener("change", (e) => {
      libraryService.setCachedOnly(e.target.checked);
      refreshLibrary();
    });
  }

  // Search input debounced
  const searchInput = document.getElementById("library-search-input");
  if (searchInput) {
    searchInput.addEventListener(
      "input",
      debounce((e) => {
        libraryService.setSearchQuery(e.target.value);
        render();
      }, 150)
    );
  }

  // Delegated delete event on grid
  const gridEl = document.getElementById("library-grid");
  if (gridEl) {
    gridEl.addEventListener("click", async (e) => {
      const btn = e.target.closest('button[data-action="delete"]');
      if (!btn) return;
      const mediaId = btn.dataset.id;
      const title = btn.dataset.title || "questo titolo";

      if (!confirm(`Sei sicuro di voler rimuovere "${title}" dalla tua libreria?\nI dati del titolo verranno eliminati, ma i file su disco non saranno toccati.`)) {
        return;
      }

      try {
        await libraryService.deleteItem(mediaId);
        showToast(`"${title}" rimosso dalla libreria`, "success");
        const totalBadge = document.getElementById("library-total-badge");
        if (totalBadge) {
          totalBadge.textContent = `${libraryService.items.length} titoli`;
        }
        render();
      } catch (err) {
        showToast("Errore durante la rimozione del titolo", "error");
      }
    });
  }
}

// Initialise page
document.addEventListener("DOMContentLoaded", () => {
  setupEvents();
  refreshLibrary();
});
