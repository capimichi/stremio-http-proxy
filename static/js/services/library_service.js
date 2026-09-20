import { HubClient } from "../clients/hub_client.js";

export class LibraryService {
  constructor() {
    this.items = [];
    this.filterType = "all";
    this.cachedOnly = false;
    this.searchQuery = "";
  }

  async fetchLibrary() {
    const data = await HubClient.getLibrary({
      type: this.filterType,
      cachedOnly: this.cachedOnly,
    });
    this.items = data.items || [];
    return {
      items: this.items,
      total: data.total || this.items.length,
    };
  }

  setFilterType(type) {
    this.filterType = type;
  }

  setCachedOnly(enabled) {
    this.cachedOnly = enabled;
  }

  setSearchQuery(query) {
    this.searchQuery = query;
  }

  getFilteredItems() {
    let result = this.items;

    if (this.searchQuery.trim()) {
      const q = this.searchQuery.toLowerCase().trim();
      result = result.filter((item) => {
        const matchTitle = item.title && item.title.toLowerCase().includes(q);
        const matchYear = item.year && item.year.includes(q);
        const matchId = item.id && item.id.toLowerCase().includes(q);
        return matchTitle || matchYear || matchId;
      });
    }

    return result;
  }

  async deleteItem(mediaId) {
    await HubClient.deleteLibraryMedia(mediaId);
    this.items = this.items.filter((i) => i.id !== mediaId);
  }
}
