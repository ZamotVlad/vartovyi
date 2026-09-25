"use strict";

(() => {
  const REFRESH_MS = 30_000;
  const SLUG = /^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/;
  const LABELS = { up: "Працює", degraded: "Повільно", down: "Недоступний" };
  const FAILURES = {
    timeout: "Не відповів вчасно",
    dns_error: "Домен не знайдено (DNS)",
    tls_error: "Помилка TLS-сертифіката",
    connection_error: "Не вдалося з'єднатися",
  };

  const $ = (id) => document.getElementById(id);
  const state = { user: null, monitors: [], latest: new Map() };

  if (!Api.tokens.access()) {
    Api.toLogin();
    return;
  }

  // ---------- форматування ----------

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function relative(iso) {
    const seconds = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
    if (seconds < 10) return "щойно";
    if (seconds < 60) return `${seconds} с тому`;
    const minutes = Math.round(seconds / 60);
    if (minutes < 60) return `${minutes} хв тому`;
    const hours = Math.round(minutes / 60);
    if (hours < 24) return `${hours} год тому`;
    return new Date(iso).toLocaleDateString("uk-UA");
  }

  function statusOf(monitor) {
    if (!monitor.is_active) return "paused";
    return state.latest.get(monitor.id)?.status ?? "pending";
  }

  // ---------- рендер ----------

  function renderTally() {
    const counts = { up: 0, degraded: 0, down: 0 };
    for (const monitor of state.monitors) {
      const status = statusOf(monitor);
      if (status in counts) counts[status] += 1;
    }
    const tally = $("tally");
    tally.replaceChildren();
    if (!state.monitors.length) return;
    for (const [status, word] of [["up", "працюють"], ["degraded", "повільно"], ["down", "недоступні"]]) {
      const item = el("span");
      item.append(el("span", `lamp lamp--${status}`), `${counts[status]} ${word}`);
      item.firstChild.setAttribute("aria-hidden", "true");
      tally.append(item);
    }
  }

  function renderRow(monitor) {
    const check = state.latest.get(monitor.id);
    const status = statusOf(monitor);
    const stateText =
      LABELS[status] ?? (status === "paused" ? "На паузі" : "Очікує першої перевірки");

    const row = el("li", "signal");
    row.dataset.id = monitor.id;

    const lamp = el("span", `lamp lamp--${status in LABELS ? status : "unknown"}`);
    lamp.setAttribute("aria-hidden", "true");

    const main = el("div", "signal__main");
    const name = el("span", "signal__name", monitor.name);
    name.append(el("span", "visually-hidden", `: ${stateText}`));
    const url = el("span", "signal__url data", monitor.url);
    url.title = monitor.url;
    const note =
      status === "up" || !check ? stateText : FAILURES[check.failure] ?? check.reason ?? stateText;
    main.append(name, url, el("span", "signal__state", note));

    const code = el("span", "signal__code data", check?.status_code ?? "-");
    const ms = el("span", "signal__ms data", check ? `${Math.round(check.elapsed_ms)} мс` : "-");
    const when = el("span", "signal__when data", check ? relative(check.created_at) : "-");
    if (check) when.title = new Date(check.created_at).toLocaleString("uk-UA");

    const actions = el("div", "signal__actions");
    const publicToggle = el("label", "check");
    const box = document.createElement("input");
    box.type = "checkbox";
    box.className = "switch";
    box.setAttribute("role", "switch");
    box.checked = monitor.is_public;
    box.dataset.action = "public";
    publicToggle.append(box, el("span", "signal__state", "Публічний"));
    const checkNow = el("button", "btn btn--ghost btn--small", "Перевірити");
    checkNow.type = "button";
    checkNow.dataset.action = "check";
    checkNow.disabled = !monitor.is_active;
    const remove = el("button", "linkbtn", "Видалити");
    remove.type = "button";
    remove.dataset.action = "delete";
    for (const button of [checkNow, remove]) button.setAttribute("aria-label", `${button.textContent}: ${monitor.name}`);
    box.setAttribute("aria-label", `Показувати ${monitor.name} на сторінці статусу`);
    actions.append(publicToggle, checkNow, remove);

    row.append(lamp, main, code, ms, when, actions);
    return row;
  }

  function render() {
    $("monitors").replaceChildren(...state.monitors.map(renderRow));
    $("empty").hidden = state.monitors.length > 0;
    renderTally();
    $("refreshed").textContent = state.monitors.length
      ? `Оновлено о ${new Date().toLocaleTimeString("uk-UA")}, далі автоматично кожні 30 с`
      : "";
  }

  function renderStatusPage() {
    const slug = state.user.status_slug;
    $("status-link").hidden = !slug;
    $("slug-form").hidden = Boolean(slug);
    if (slug) {
      const link = $("status-url");
      link.href = `/status/${encodeURIComponent(slug)}`;
      link.textContent = `${window.location.origin}/status/${slug}`;
    }
  }

  function showLoadError(error) {
    $("load-error").hidden = !error;
    $("load-error-text").textContent = error ? error.message : "";
  }

  // ---------- дані ----------

  async function loadMonitors() {
    try {
      const page = await Api.request("/monitors?limit=100&sort=name");
      // Останній стан кожного монітора. Паралельно, бо на сторінці до 100 рядків
      const latest = await Promise.all(
        page.items.map((m) =>
          Api.request(`/monitors/${m.id}/checks?limit=1`).then((p) => [m.id, p.items[0]])
        )
      );
      state.monitors = page.items;
      state.latest = new Map(latest.filter(([, check]) => check));
      showLoadError(null);
      render();
    } catch (error) {
      showLoadError(error);
    }
  }

  // ---------- форми ----------

  function fieldError(form, name, message) {
    const input = form.elements[name];
    const slot = $(`${name}-error`);
    if (slot) slot.textContent = message || "";
    if (input) input.setAttribute("aria-invalid", message ? "true" : "false");
  }

  function applyServerErrors(form, error, knownFields, fallback) {
    const fields = Object.entries(error.fields ?? {}).filter(([f]) => knownFields.includes(f));
    for (const [field, message] of fields) fieldError(form, field, message);
    if (!fields.length) {
      fallback.textContent = error.message;
      fallback.hidden = false;
    }
  }

  const MONITOR_FIELDS = [
    "name", "url", "interval_seconds", "timeout_ms", "expected_status", "max_response_ms", "keyword",
  ];

  function readMonitorForm(form) {
    const value = (n) => form.elements[n].value.trim();
    const errors = {};
    const data = {
      name: value("name"),
      url: value("url"),
      interval_seconds: Number(value("interval_seconds")),
      timeout_ms: Number(value("timeout_ms")),
      expected_status: Number(value("expected_status")),
      max_response_ms: value("max_response_ms") ? Number(value("max_response_ms")) : null,
      keyword: value("keyword") || null,
      is_public: form.elements.is_public.checked,
    };

    if (!data.name) errors.name = "Вкажіть назву, наприклад «API продакшн»";
    try {
      const parsed = new URL(data.url);
      if (!["http:", "https:"].includes(parsed.protocol)) throw new Error();
    } catch {
      errors.url = "Потрібна повна адреса з http:// або https://";
    }
    const int = (v) => Number.isInteger(v);
    if (!int(data.interval_seconds) || data.interval_seconds < 30 || data.interval_seconds > 86400)
      errors.interval_seconds = "Від 30 до 86400 секунд";
    if (!int(data.timeout_ms) || data.timeout_ms < 100 || data.timeout_ms > 60000)
      errors.timeout_ms = "Від 100 до 60000 мс";
    else if (!errors.interval_seconds && data.timeout_ms > data.interval_seconds * 1000)
      errors.timeout_ms = "Таймаут не може бути довшим за інтервал";
    if (!int(data.expected_status) || data.expected_status < 100 || data.expected_status > 599)
      errors.expected_status = "HTTP-код від 100 до 599";
    if (data.max_response_ms !== null) {
      if (!int(data.max_response_ms) || data.max_response_ms < 1)
        errors.max_response_ms = "Ціле число мілісекунд";
      else if (!errors.timeout_ms && data.max_response_ms > data.timeout_ms)
        errors.max_response_ms = "Поріг має бути меншим за таймаут";
    }
    return { data, errors };
  }

  async function onCreate(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const notice = $("create-error");
    notice.hidden = true;
    const { data, errors } = readMonitorForm(form);
    for (const field of MONITOR_FIELDS) fieldError(form, field, errors[field]);
    const first = MONITOR_FIELDS.find((f) => errors[f]);
    if (first) {
      form.elements[first].focus();
      return;
    }

    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    try {
      const monitor = await Api.request("/monitors", { method: "POST", json: data });
      form.reset();
      // Перший результат одразу, не чекаючи такту планувальника
      await Api.request(`/monitors/${monitor.id}/checks`, { method: "POST" }).catch(() => null);
      await loadMonitors();
      $("monitors").querySelector(`[data-id="${monitor.id}"] button`)?.focus();
    } catch (error) {
      applyServerErrors(form, error, MONITOR_FIELDS, notice);
    } finally {
      button.disabled = false;
    }
  }

  async function onSlug(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const slug = form.elements.status_slug.value.trim().toLowerCase();
    let message = "";
    if (slug.length < 3 || slug.length > 50) message = "Від 3 до 50 символів";
    else if (!SLUG.test(slug)) message = "Лише a-z, 0-9 і дефіс, без дефіса на початку чи в кінці";
    fieldError(form, "status_slug", message);
    if (message) {
      form.elements.status_slug.focus();
      return;
    }
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    try {
      state.user = await Api.request("/auth/me", { method: "PATCH", json: { status_slug: slug } });
      renderStatusPage();
      $("status-url").focus();
    } catch (error) {
      const text = error.code === "status_slug_taken" ? "Цю адресу вже зайнято, оберіть іншу" : error.message;
      fieldError(form, "status_slug", text);
    } finally {
      button.disabled = false;
    }
  }

  async function onRowAction(event) {
    const target = event.target.closest("[data-action]");
    if (!target) return;
    const row = target.closest(".signal");
    const id = row.dataset.id;
    const monitor = state.monitors.find((m) => m.id === id);
    const action = target.dataset.action;
    if (action === "delete" && !window.confirm(`Видалити монітор «${monitor.name}» разом з історією?`)) return;

    row.dataset.busy = "true";
    try {
      if (action === "public") {
        await Api.request(`/monitors/${id}`, { method: "PATCH", json: { is_public: target.checked } });
        monitor.is_public = target.checked;
      } else if (action === "check") {
        const check = await Api.request(`/monitors/${id}/checks`, { method: "POST" });
        state.latest.set(id, check);
      } else if (action === "delete") {
        await Api.request(`/monitors/${id}`, { method: "DELETE" });
        state.monitors = state.monitors.filter((m) => m.id !== id);
      }
      showLoadError(null);
      render();
      if (action !== "delete") {
        $("monitors").querySelector(`[data-id="${id}"] [data-action="${action}"]`)?.focus();
      }
    } catch (error) {
      if (action === "public") target.checked = !target.checked;
      row.dataset.busy = "false";
      showLoadError(error);
    }
  }

  // ---------- старт ----------

  async function start() {
    try {
      state.user = await Api.request("/auth/me");
    } catch (error) {
      if (error.status === 401) return; // Api уже веде на /login
      $("boot").textContent = error.message;
      const retry = el("button", "linkbtn", "Спробувати ще раз");
      retry.type = "button";
      retry.addEventListener("click", () => window.location.reload());
      $("boot").append(" ", retry);
      return;
    }
    $("user-email").textContent = state.user.email;
    $("boot").hidden = true;
    $("app").hidden = false;
    renderStatusPage();
    await loadMonitors();
    window.setInterval(loadMonitors, REFRESH_MS);
  }

  document.querySelector(".empty .btn").addEventListener("click", (e) => {
    e.preventDefault();
    $("name").focus();
  });
  $("logout").addEventListener("click", () => Api.logout());
  $("retry").addEventListener("click", loadMonitors);
  $("create-form").addEventListener("submit", onCreate);
  $("slug-form").addEventListener("submit", onSlug);
  $("status-edit").addEventListener("click", () => {
    $("status-link").hidden = true;
    $("slug-form").hidden = false;
    $("status_slug").value = state.user.status_slug ?? "";
    $("status_slug").focus();
  });
  $("monitors").addEventListener("click", (e) => {
    if (e.target.closest("[data-action]")?.dataset.action !== "public") onRowAction(e);
  });
  $("monitors").addEventListener("change", (e) => {
    if (e.target.dataset.action === "public") onRowAction(e);
  });

  start();
})();
