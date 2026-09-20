/**
 * Base HTTP API Client
 */

export class ApiClient {
  static async request(url, options = {}) {
    const defaultHeaders = {
      Accept: "application/json",
    };

    if (options.body && typeof options.body === "object" && !(options.body instanceof FormData)) {
      defaultHeaders["Content-Type"] = "application/json";
      options.body = JSON.stringify(options.body);
    }

    const config = {
      ...options,
      headers: {
        ...defaultHeaders,
        ...options.headers,
      },
    };

    try {
      const response = await fetch(url, config);
      if (!response.ok) {
        let errMessage = `HTTP error ${response.status}`;
        try {
          const errData = await response.json();
          if (errData && errData.detail) errMessage = errData.detail;
        } catch {
          // ignore json parse error
        }
        throw new Error(errMessage);
      }
      return await response.json();
    } catch (error) {
      console.error(`API Error [${options.method || "GET"} ${url}]:`, error);
      throw error;
    }
  }

  static get(url, options = {}) {
    return this.request(url, { ...options, method: "GET" });
  }

  static post(url, body, options = {}) {
    return this.request(url, { ...options, method: "POST", body });
  }

  static delete(url, options = {}) {
    return this.request(url, { ...options, method: "DELETE" });
  }
}
