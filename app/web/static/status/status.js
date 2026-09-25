"use strict";

const REFRESH_MS = 60_000;
const STATUS_LABELS = { up: "Працює", degraded: "Повільно", down: "Недоступний" };
const BANNERS = {
  up: "Усі системи працюють",
  degraded: "Деякі сервіси працюють повільно",
  down: "Є збої в роботі сервісів",
  unknown: "Даних про перевірки ще немає",
};

const slug = decodeURIComponent(window.location.pathname.split("/").filter(Boolean).pop() || "");

function overallStatus(monitors) {
  const statuses = monitors.map((m) => m.current_status).filter(Boolean);
  if (statuses.length === 0) return "unknown";
  if (statuses.includes("down")) return "down";
  if (statuses.includes("degraded")) return "degraded";
  return "up";
}

function formatPercent(uptime) {
  return uptime.percent === null ? "-" : `${uptime.percent.toFixed(2)}%`;
}

function formatRelative(isoDate) {
  const seconds = Math.round((Date.now() - new Date(isoDate).getTime()) / 1000);
  if (seconds < 60) return "щойно";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} хв тому`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} год тому`;
  return new Date(isoDate).toLocaleString("uk-UA");
}

function setBanner(status, text) {
  document.getElementById("banner-lamp").className = `lamp lamp--${status}`;
  document.getElementById("banner-text").textContent = text;
}

function renderMonitor(template, monitor) {
  const node = template.content.firstElementChild.cloneNode(true);
  const status = monitor.current_status || "unknown";
  node.querySelector(".lamp").className = `lamp lamp--${status}`;
  // Лише textContent: назви задає користувач, вставка як HTML відкрила б шлях для XSS
  node.querySelector(".signal__name").textContent = monitor.name;
  const label = STATUS_LABELS[status] || "Немає даних";
  node.querySelector(".signal__state").textContent = monitor.last_checked_at
    ? `${label}, перевірено ${formatRelative(monitor.last_checked_at)}`
    : "Ще не перевірявся";
  for (const cell of node.querySelectorAll("[data-window]")) {
    cell.textContent = formatPercent(monitor[cell.dataset.window]);
  }
  return node;
}

function render(page) {
  const list = document.getElementById("monitors");
  const template = document.getElementById("monitor-template");
  list.replaceChildren(...page.monitors.map((m) => renderMonitor(template, m)));
  document.getElementById("empty").hidden = page.monitors.length > 0;
  const status = overallStatus(page.monitors);
  setBanner(status, BANNERS[status]);
  document.getElementById("updated").textContent =
    `Оновлено о ${new Date(page.generated_at).toLocaleTimeString("uk-UA")}, далі щохвилини`;
}

async function load() {
  try {
    const response = await fetch(`/api/v1/status/${encodeURIComponent(slug)}`, {
      headers: { Accept: "application/json" },
    });
    if (response.status === 404) {
      setBanner("unknown", "Сторінку статусу не знайдено");
      return false;
    }
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    render(await response.json());
  } catch {
    // Попередні дані лишаються на екрані, міняємо лише банер
    setBanner("unknown", "Не вдалося оновити дані, повторимо за хвилину");
  }
  return true;
}

async function start() {
  document.getElementById("title").textContent = slug;
  document.title = `${slug} - статус сервісів`;
  if (await load()) window.setInterval(load, REFRESH_MS);
}

start();
