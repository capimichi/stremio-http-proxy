import { ApiClient } from "./api_client.js";

export class BrowserClient {
  static search(query, type = "series", page = 1) {
    return ApiClient.get(`/api/browser/search?q=${encodeURIComponent(query)}&type=${encodeURIComponent(type)}&page=${encodeURIComponent(page)}`);
  }

  static resolve(tmdbId, type = "series") {
    return ApiClient.get(`/api/browser/resolve?tmdb_id=${encodeURIComponent(tmdbId)}&type=${encodeURIComponent(type)}`);
  }

  static getContent(type, id, season = null, episode = null) {
    let url = `/api/browser/content?type=${encodeURIComponent(type)}&id=${encodeURIComponent(id)}`;
    if (season !== null && season !== undefined) url += `&season=${encodeURIComponent(season)}`;
    if (episode !== null && episode !== undefined) url += `&episode=${encodeURIComponent(episode)}`;
    return ApiClient.get(url);
  }
}
