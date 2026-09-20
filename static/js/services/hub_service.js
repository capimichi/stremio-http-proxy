import { CacheClient } from "../clients/cache_client.js";
import { HubClient } from "../clients/hub_client.js";

export class HubService {
  constructor() {
    this.recentMedia = [];
    this.downloadsPayload = null;
  }

  async fetchRecent(limit = 12) {
    const data = await HubClient.getRecentMedia(limit);
    this.recentMedia = data.items || [];
    return this.recentMedia;
  }

  async fetchDownloads(page = 1, limit = 5) {
    this.downloadsPayload = await CacheClient.getDownloads({ page, limit });
    return this.downloadsPayload;
  }

  getHeroItem() {
    return this.recentMedia.length > 0 ? this.recentMedia[0] : null;
  }
}
