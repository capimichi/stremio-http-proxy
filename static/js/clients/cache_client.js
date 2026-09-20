import { ApiClient } from "./api_client.js";

export class CacheClient {
  static getDownloads({ page = 1, limit = 10, search = "", status = "" } = {}) {
    let url = `/downloads?page=${encodeURIComponent(page)}&limit=${encodeURIComponent(limit)}`;
    if (search) url += `&search=${encodeURIComponent(search)}`;
    if (status) url += `&status=${encodeURIComponent(status)}`;
    return ApiClient.get(url);
  }
}
