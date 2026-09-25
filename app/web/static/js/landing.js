"use strict";

// Для вже залогіненого користувача головна кнопка веде одразу в панель
if (Api.tokens.access()) {
  const nav = document.getElementById("nav");
  const link = document.createElement("a");
  link.className = "btn btn--small";
  link.href = "/dashboard";
  link.textContent = "Панель моніторів";
  nav.replaceChildren(link);
}
