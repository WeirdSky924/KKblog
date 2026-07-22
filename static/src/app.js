import Alpine from "alpinejs";
import "htmx.org";
import {
  ArrowLeft,
  CircleCheck,
  CircleX,
  Info,
  RotateCw,
  TriangleAlert,
  X,
  createIcons,
} from "lucide";

import { normalizeTheme, storeTheme } from "./theme-values.js";

const availableIcons = {
  ArrowLeft,
  CircleCheck,
  CircleX,
  Info,
  RotateCw,
  TriangleAlert,
  X,
};
const RETURN_FOCUS_KEY = "kaj.error-return-focus";
const RETURN_FOCUS_REQUEST_KEY = "kaj.error-return-focus-requested";

function writeSessionValue(key, value) {
  try {
    window.sessionStorage.setItem(key, value);
  } catch {
    // Session storage is optional; history navigation still works without it.
  }
}

function takeSessionValue(key) {
  try {
    const value = window.sessionStorage.getItem(key);
    window.sessionStorage.removeItem(key);
    return value;
  } catch {
    return null;
  }
}

function restoreErrorOriginFocus() {
  if (takeSessionValue(RETURN_FOCUS_REQUEST_KEY) !== "true") {
    return;
  }
  const originId = takeSessionValue(RETURN_FOCUS_KEY);
  if (!originId) {
    return;
  }
  const origin = document.getElementById(originId);
  if (origin instanceof HTMLElement) {
    requestAnimationFrame(() => origin.focus({ preventScroll: true }));
  }
}

function restoreSubmitState() {
  document.querySelectorAll("form[data-submit-once]").forEach((form) => {
    delete form.dataset.submitting;
    form.removeAttribute("aria-busy");
    form
      .querySelectorAll("button[type='submit'], input[type='submit']")
      .forEach((control) => control.removeAttribute("aria-disabled"));
  });
}

function initializeIcons(root = document) {
  createIcons({
    root,
    icons: availableIcons,
    attrs: {
      "aria-hidden": "true",
      focusable: "false",
      width: "24",
      height: "24",
    },
  });
}

function initializeConfirmDialogs(root = document) {
  root.querySelectorAll?.("[data-confirm-dialog]").forEach((dialog) => {
    if (!(dialog instanceof HTMLDialogElement)) {
      return;
    }
    if (dialog.dataset.bound !== "true") {
      dialog.dataset.bound = "true";
      dialog.querySelector("[data-dialog-cancel]")?.addEventListener("click", () => {
        dialog.close("cancel");
      });
      dialog.addEventListener("close", () => {
        const trigger = dialog.id
          ? document.querySelector(
              `[data-dialog-trigger][aria-controls="${dialog.id}"]`,
            )
          : document.querySelector("[data-dialog-trigger]");
        if (dialog.returnValue === "cancel") {
          const url = new URL(window.location.href);
          url.searchParams.delete("confirm");
          url.hash =
            trigger instanceof HTMLElement
              ? trigger.dataset.dialogReturnHash || ""
              : "";
          window.history.replaceState(null, "", url);
        }
        if (trigger instanceof HTMLElement) {
          requestAnimationFrame(() => trigger.focus({ preventScroll: true }));
        }
      });
    }
    if (dialog.hasAttribute("data-auto-modal")) {
      if (dialog.open) {
        dialog.removeAttribute("open");
      }
      dialog.showModal();
      const cancel = dialog.querySelector("[data-dialog-cancel]");
      if (cancel instanceof HTMLElement) {
        window.requestAnimationFrame(() => {
          if (dialog.open) {
            cancel.focus({ preventScroll: true });
          }
        });
      }
    }
  });
}

function applyTheme(value, { persist = true } = {}) {
  const theme = normalizeTheme(value);
  if (!theme) {
    return false;
  }
  document.documentElement.dataset.theme = theme;
  if (persist) {
    storeTheme(theme);
  }
  document.querySelectorAll("[data-theme-value]").forEach((control) => {
    const selected = control.getAttribute("data-theme-value") === theme;
    if (control.hasAttribute("aria-pressed")) {
      control.setAttribute("aria-pressed", String(selected));
    }
    if (control instanceof HTMLInputElement) {
      control.checked = selected;
    }
  });
  document.dispatchEvent(
    new CustomEvent("kaj:theme-changed", { detail: { theme } }),
  );
  return true;
}

function focusInsertedError(root) {
  const error = root.querySelector?.("[data-error-focus]");
  if (error instanceof HTMLElement) {
    requestAnimationFrame(() => error.focus());
  }
}

document.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof Element)) {
    return;
  }

  const back = target.closest("[data-error-back]");
  if (back) {
    if (window.history.length > 1) {
      writeSessionValue(RETURN_FOCUS_REQUEST_KEY, "true");
      window.history.back();
    } else {
      window.location.assign("/");
    }
    return;
  }

  if (target.closest("[data-error-retry], [data-maintenance-retry]")) {
    window.location.reload();
    return;
  }

  const dismiss = target.closest("[data-feedback-dismiss]");
  if (dismiss) {
    const item = dismiss.closest("[data-feedback-item]");
    const region = item?.closest("#global-feedback");
    item?.remove();
    if (event.detail === 0 && region instanceof HTMLElement) {
      region.focus({ preventScroll: true });
    }
    return;
  }

  const themeControl = target.closest("[data-theme-value]");
  if (themeControl) {
    applyTheme(themeControl.getAttribute("data-theme-value"));
    return;
  }

  const errorOrigin = target.closest("[data-error-origin]");
  if (errorOrigin instanceof HTMLElement) {
    if (!errorOrigin.id) {
      errorOrigin.id = `error-origin-${Date.now().toString(36)}`;
    }
    writeSessionValue(RETURN_FOCUS_KEY, errorOrigin.id);
  }
});

document.addEventListener("kaj:theme-request", (event) => {
  applyTheme(event.detail?.theme);
});

document.addEventListener("submit", (event) => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement) || !form.hasAttribute("data-submit-once")) {
    return;
  }
  if (form.dataset.submitting === "true") {
    event.preventDefault();
    return;
  }
  form.dataset.submitting = "true";
  form.setAttribute("aria-busy", "true");
  requestAnimationFrame(() => {
    form.querySelectorAll("button[type='submit'], input[type='submit']").forEach((control) => {
      control.setAttribute("aria-disabled", "true");
    });
  });
});

document.addEventListener("htmx:afterSwap", (event) => {
  const root = event.detail?.target ?? document;
  initializeIcons(root);
  initializeConfirmDialogs(root);
  focusInsertedError(root);
});

window.addEventListener("pageshow", () => {
  restoreSubmitState();
  restoreErrorOriginFocus();
});

window.Alpine = Alpine;
Alpine.start();
initializeIcons();
initializeConfirmDialogs();
focusInsertedError(document);
applyTheme(document.documentElement.dataset.theme, { persist: false });
