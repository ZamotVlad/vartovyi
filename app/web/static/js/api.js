"use strict";

// Спільний клієнт API: токени, автоматичний refresh, зрозумілі помилки.
const Api = (() => {
  const ACCESS = "vtv.access";
  const REFRESH = "vtv.refresh";
  const BASE = "/api/v1";

  const MESSAGES = {
    0: "Сервер недоступний. Перевірте з'єднання і спробуйте ще раз.",
    500: "На сервері сталася помилка. Ми вже знаємо про неї в логах.",
    502: "Сервер тимчасово недоступний. Спробуйте за хвилину.",
    503: "Сервер тимчасово недоступний. Спробуйте за хвилину.",
  };

  class ApiError extends Error {
    constructor(status, code, message, fields = {}) {
      super(message);
      this.status = status;
      this.code = code;
      this.fields = fields;
    }
  }

  function storage(fn) {
    try {
      return fn(window.localStorage);
    } catch {
      return null;
    }
  }

  const tokens = {
    access: () => storage((s) => s.getItem(ACCESS)),
    refresh: () => storage((s) => s.getItem(REFRESH)),
    save(pair) {
      storage((s) => {
        s.setItem(ACCESS, pair.access_token);
        s.setItem(REFRESH, pair.refresh_token);
      });
    },
    clear() {
      storage((s) => {
        s.removeItem(ACCESS);
        s.removeItem(REFRESH);
      });
    },
  };

  async function toError(response) {
    let body = null;
    try {
      body = await response.json();
    } catch {
      // Тіло не JSON: наприклад, HTML від проксі
    }
    const fields = {};
    for (const detail of body?.details ?? []) {
      if (detail.field && !fields[detail.field]) fields[detail.field] = detail.message;
    }
    const message =
      MESSAGES[response.status] ?? body?.error?.message ?? "Не вдалося виконати запит.";
    return new ApiError(response.status, body?.error?.code ?? "unknown", message, fields);
  }

  async function raw(path, options = {}) {
    let response;
    try {
      response = await fetch(BASE + path, options);
    } catch {
      throw new ApiError(0, "network", MESSAGES[0]);
    }
    if (!response.ok) throw await toError(response);
    return response.status === 204 ? null : response.json();
  }

  // Один refresh на всі паралельні запити, що отримали 401
  let refreshing = null;

  function refreshTokens() {
    const refreshToken = tokens.refresh();
    if (!refreshToken) return Promise.resolve(false);
    refreshing ??= raw("/auth/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
      .then((pair) => {
        tokens.save(pair);
        return true;
      })
      .catch((error) => {
        if (error.status === 0) throw error;
        return false;
      })
      .finally(() => {
        refreshing = null;
      });
    return refreshing;
  }

  function toLogin() {
    tokens.clear();
    const next = encodeURIComponent(window.location.pathname);
    window.location.replace(`/login?next=${next}`);
  }

  async function request(path, { method = "GET", json } = {}, retried = false) {
    const headers = { Accept: "application/json" };
    const access = tokens.access();
    if (access) headers.Authorization = `Bearer ${access}`;
    if (json !== undefined) headers["Content-Type"] = "application/json";
    try {
      return await raw(path, {
        method,
        headers,
        body: json === undefined ? undefined : JSON.stringify(json),
      });
    } catch (error) {
      if (error.status !== 401 || retried) {
        if (error.status === 401) toLogin();
        throw error;
      }
      if (await refreshTokens()) return request(path, { method, json }, true);
      toLogin();
      throw error;
    }
  }

  async function login(email, password) {
    const pair = await raw("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ username: email, password }),
    });
    tokens.save(pair);
  }

  function register(email, password) {
    return raw("/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
  }

  async function logout() {
    const refreshToken = tokens.refresh();
    try {
      if (refreshToken) {
        await request("/auth/logout", { method: "POST", json: { refresh_token: refreshToken } }, true);
      }
    } catch {
      // Навіть якщо сервер не відповів, локально користувач виходить
    }
    tokens.clear();
    window.location.replace("/login");
  }

  return { ApiError, tokens, request, login, register, logout, toLogin };
})();
