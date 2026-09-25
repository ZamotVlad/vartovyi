"use strict";

(() => {
  const form = document.getElementById("auth-form");
  const mode = form.dataset.mode;
  const formError = document.getElementById("form-error");
  const button = form.querySelector("button[type=submit]");
  const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

  function nextUrl() {
    const next = new URLSearchParams(window.location.search).get("next");
    // Лише внутрішні шляхи: інакше ?next= став би відкритим редиректом
    return next && next.startsWith("/") && !next.startsWith("//") ? next : "/dashboard";
  }

  if (Api.tokens.access()) window.location.replace(nextUrl());

  function setFieldError(name, message) {
    const input = form.elements[name];
    const slot = document.getElementById(`${name}-error`);
    if (!input || !slot) return;
    slot.textContent = message || "";
    input.setAttribute("aria-invalid", message ? "true" : "false");
  }

  function showFormError(message) {
    formError.textContent = message;
    formError.hidden = !message;
  }

  function validate(values) {
    const errors = {};
    if (!EMAIL.test(values.email)) errors.email = "Введіть email у форматі name@example.com";
    if (mode === "register") {
      if (values.password.length < 8) errors.password = "Пароль має містити щонайменше 8 символів";
      else if (new TextEncoder().encode(values.password).length > 72)
        errors.password = "Пароль задовгий: максимум 72 байти";
      if (values.password2 !== values.password) errors.password2 = "Паролі не збігаються";
    } else if (!values.password) {
      errors.password = "Введіть пароль";
    }
    return errors;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const values = {
      email: form.elements.email.value.trim(),
      password: form.elements.password.value,
      password2: form.elements.password2?.value ?? "",
    };
    const errors = validate(values);
    for (const name of ["email", "password", "password2"]) setFieldError(name, errors[name]);
    showFormError("");
    const firstInvalid = Object.keys(errors)[0];
    if (firstInvalid) {
      form.elements[firstInvalid].focus();
      return;
    }

    button.disabled = true;
    try {
      if (mode === "register") await Api.register(values.email, values.password);
      await Api.login(values.email, values.password);
      window.location.replace(nextUrl());
    } catch (error) {
      if (error.code === "email_already_registered") {
        setFieldError("email", "Цей email уже зареєстровано. Спробуйте увійти.");
      } else if (error.code === "invalid_credentials") {
        showFormError("Невірний email або пароль.");
      } else if (error.fields && Object.keys(error.fields).length) {
        for (const [field, message] of Object.entries(error.fields)) setFieldError(field, message);
      } else {
        showFormError(error.message);
      }
    } finally {
      button.disabled = false;
    }
  });
})();
