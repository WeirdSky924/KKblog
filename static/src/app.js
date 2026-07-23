import Alpine from "alpinejs";
import "htmx.org";
import {
  ArrowLeft,
  CircleCheck,
  CircleX,
  ImageUp,
  Info,
  RotateCw,
  Trash2,
  TriangleAlert,
  X,
  createIcons,
} from "lucide";

import { normalizeTheme, storeTheme } from "./theme-values.js";

const availableIcons = {
  ArrowLeft,
  CircleCheck,
  CircleX,
  ImageUp,
  Info,
  RotateCw,
  Trash2,
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

function setMediaPickerState(picker, state) {
  const order = ["select", "validate", "ready"];
  const activeIndex =
    state === "ready" ? 2 : state === "uploading" || state === "error" ? 1 : 0;
  picker.dataset.mediaState = state;
  if (state === "uploading") {
    picker.setAttribute("aria-busy", "true");
  } else {
    picker.removeAttribute("aria-busy");
  }
  picker.querySelectorAll("[data-media-step]").forEach((step) => {
    const index = order.indexOf(step.dataset.mediaStep);
    step.toggleAttribute("data-complete", index >= 0 && index < activeIndex);
    if (index === activeIndex) {
      step.setAttribute("aria-current", "step");
    } else {
      step.removeAttribute("aria-current");
    }
  });
}

function uploadResultNode(source) {
  const template = document.createElement("template");
  template.innerHTML = source.trim();
  const node = template.content.querySelector("[data-media-upload-result]");
  node?.querySelector("input[type='hidden']")?.remove();
  return node;
}

function initializeMediaPickers(root = document) {
  root.querySelectorAll?.("[data-media-picker]").forEach((picker) => {
    if (!(picker instanceof HTMLElement) || picker.dataset.bound === "true") {
      return;
    }
    picker.dataset.bound = "true";
    const input = picker.querySelector("[data-media-file]");
    const choose = picker.querySelector("[data-media-choose]");
    const value = picker.querySelector("[data-media-value]");
    const preview = picker.querySelector("[data-media-preview]");
    const empty = picker.querySelector("[data-media-empty]");
    const dropzone = picker.querySelector("[data-media-dropzone]");
    const result = picker.querySelector("[data-media-result]");
    const retry = picker.querySelector("[data-media-retry]");
    const remove = picker.querySelector("[data-media-remove]");
    const progressWrap = picker.querySelector("[data-media-progress-wrap]");
    const progress = picker.querySelector("[data-media-progress]");
    const csrf = picker.querySelector("input[name='csrfmiddlewaretoken']");
    if (
      !(input instanceof HTMLInputElement) ||
      !(value instanceof HTMLInputElement) ||
      !(preview instanceof HTMLImageElement) ||
      !(result instanceof HTMLElement) ||
      !(progress instanceof HTMLProgressElement)
    ) {
      return;
    }

    let selectedFile = null;
    let previewUrl = null;
    const favicon = document.querySelector("[data-site-favicon]");

    const clearPreviewUrl = () => {
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
        previewUrl = null;
      }
    };

    const showSelectedPreview = (file) => {
      clearPreviewUrl();
      previewUrl = URL.createObjectURL(file);
      preview.hidden = true;
      preview.alt = "";
      if (empty instanceof HTMLElement) {
        empty.hidden = false;
      }
      preview.onload = () => {
        preview.alt = "所选图片预览";
        preview.hidden = false;
        if (empty instanceof HTMLElement) {
          empty.hidden = true;
        }
      };
      preview.onerror = () => {
        preview.removeAttribute("src");
        preview.alt = "";
        preview.hidden = true;
        if (empty instanceof HTMLElement) {
          empty.hidden = false;
        }
      };
      preview.src = previewUrl;
    };

    const setControlsBusy = (busy) => {
      input.disabled = busy;
      choose?.toggleAttribute("disabled", busy);
      retry?.toggleAttribute("disabled", busy);
      remove?.toggleAttribute("disabled", busy);
      dropzone?.toggleAttribute("aria-disabled", busy);
      if (progressWrap instanceof HTMLElement) {
        progressWrap.hidden = !busy;
      }
    };

    const showClientError = (message) => {
      const item = document.createElement("div");
      item.className = "media-upload-result";
      item.dataset.mediaUploadResult = "error";
      item.setAttribute("role", "alert");
      const text = document.createElement("p");
      text.className = "field-error";
      text.textContent = message;
      item.append(text);
      result.replaceChildren(item);
      retry?.removeAttribute("hidden");
      setMediaPickerState(picker, "error");
    };

    const upload = () => {
      if (!(selectedFile instanceof File)) {
        return;
      }
      const request = new XMLHttpRequest();
      const body = new FormData();
      body.append("file", selectedFile, selectedFile.name);
      setControlsBusy(true);
      retry?.setAttribute("hidden", "");
      remove?.setAttribute("hidden", "");
      progress.value = 0;
      setMediaPickerState(picker, "uploading");
      request.open("POST", picker.dataset.mediaUploadUrl || "");
      request.setRequestHeader("X-Requested-With", "XMLHttpRequest");
      if (csrf instanceof HTMLInputElement && csrf.value) {
        request.setRequestHeader("X-CSRFToken", csrf.value);
      }
      request.upload.addEventListener("progress", (event) => {
        progress.value = event.lengthComputable
          ? Math.round((event.loaded / event.total) * 100)
          : 0;
      });
      request.addEventListener("load", () => {
        setControlsBusy(false);
        const responseNode = uploadResultNode(request.responseText);
        if (responseNode) {
          result.replaceChildren(responseNode);
        }
        if (request.status === 201 && responseNode?.dataset.assetId) {
          value.value = responseNode.dataset.assetId;
          progress.value = 100;
          remove?.removeAttribute("hidden");
          retry?.setAttribute("hidden", "");
          setMediaPickerState(picker, "ready");
          if (
            picker.dataset.mediaFavicon === "true" &&
            favicon instanceof HTMLLinkElement &&
            previewUrl
          ) {
            favicon.href = previewUrl;
          }
          return;
        }
        retry?.removeAttribute("hidden");
        setMediaPickerState(picker, "error");
        if (!responseNode) {
          showClientError("图片上传未完成，请重试。");
        }
      });
      request.addEventListener("error", () => {
        setControlsBusy(false);
        showClientError("暂时无法上传图片，请重试。");
      });
      request.send(body);
    };

    const select = (file) => {
      if (input.disabled || !(file instanceof File)) {
        return;
      }
      selectedFile = file;
      result.replaceChildren();
      showSelectedPreview(file);
      setMediaPickerState(picker, "select");
      upload();
    };

    input.addEventListener("change", () => select(input.files?.[0]));
    choose?.addEventListener("click", () => input.click());
    retry?.addEventListener("click", upload);
    remove?.addEventListener("click", () => {
      selectedFile = null;
      input.value = "";
      value.value = "";
      result.replaceChildren();
      retry?.setAttribute("hidden", "");
      remove.setAttribute("hidden", "");
      clearPreviewUrl();
      preview.removeAttribute("src");
      preview.alt = "";
      preview.hidden = true;
      if (empty instanceof HTMLElement) {
        empty.hidden = false;
      }
      if (picker.dataset.mediaFavicon === "true" && favicon instanceof HTMLLinkElement) {
        favicon.href = favicon.dataset.defaultHref || favicon.href;
      }
      setMediaPickerState(picker, "empty");
      if (choose instanceof HTMLElement) {
        choose.focus();
      }
    });

    if (dropzone instanceof HTMLElement) {
      ["dragenter", "dragover"].forEach((name) => {
        dropzone.addEventListener(name, (event) => {
          event.preventDefault();
          dropzone.dataset.dragActive = "true";
        });
      });
      ["dragleave", "drop"].forEach((name) => {
        dropzone.addEventListener(name, (event) => {
          event.preventDefault();
          delete dropzone.dataset.dragActive;
        });
      });
      dropzone.addEventListener("drop", (event) => {
        select(event.dataTransfer?.files?.[0]);
      });
    }

    picker.closest("form")?.addEventListener("submit", (event) => {
      if (picker.dataset.mediaState === "uploading") {
        event.preventDefault();
        showClientError("请等待图片校验完成后再保存。");
        retry?.setAttribute("hidden", "");
        setMediaPickerState(picker, "uploading");
      }
    });
    setMediaPickerState(picker, value.value ? "ready" : "empty");
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
  if (
    event.defaultPrevented ||
    !(form instanceof HTMLFormElement) ||
    !form.hasAttribute("data-submit-once")
  ) {
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
  initializeMediaPickers(root);
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
initializeMediaPickers();
focusInsertedError(document);
applyTheme(document.documentElement.dataset.theme, { persist: false });
