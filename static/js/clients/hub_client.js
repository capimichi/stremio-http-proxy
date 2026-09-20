import { ApiClient } from "./api_client.js";

export class HubClient {
  static getRecentMedia(limit = 12) {
    return ApiClient.get(`/api/hub/recent?limit=${encodeURIComponent(limit)}`);
  }

  static getLibrary({ type = null, cachedOnly = false, limit = 500, offset = 0 } = {}) {
    let url = `/api/hub/library?limit=${encodeURIComponent(limit)}&offset=${encodeURIComponent(offset)}`;
    if (type && type !== "all") {
      url += `&type=${encodeURIComponent(type)}`;
    }
    if (cachedOnly) {
      url += `&cached_only=true`;
    }
    return ApiClient.get(url);
  }

  static deleteLibraryMedia(mediaId) {
    return ApiClient.delete(`/api/hub/library/${encodeURIComponent(mediaId)}`);
  }

  static getMediaStreams(contentId) {
    return ApiClient.get(`/api/hub/media-streams/${encodeURIComponent(contentId)}`);
  }

  static deleteStream(cacheKey) {
    return ApiClient.delete(`/api/hub/streams/${encodeURIComponent(cacheKey)}`);
  }

  static cacheSeason(payload) {
    return ApiClient.post("/api/browser/cache-season", payload);
  }

  static cacheEpisode(payload) {
    return ApiClient.post("/api/browser/cache-episode", payload);
  }

  static getTasks({ status = null, limit = 20 } = {}) {
    let url = `/api/hub/tasks?limit=${encodeURIComponent(limit)}`;
    if (status) {
      url += `&status=${encodeURIComponent(status)}`;
    }
    return ApiClient.get(url);
  }
}

