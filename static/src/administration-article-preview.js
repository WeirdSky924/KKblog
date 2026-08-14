let previewEventsBound = false;

function previewDialog() {
  const dialog = document.querySelector("[data-admin-article-preview-dialog]");
  return dialog instanceof HTMLDialogElement ? dialog : null;
}

function previewSource(event) {
  return event.detail?.elt?.closest?.(
    "[data-article-preview-trigger], [data-article-preview-version-form]",
  );
}

function setLoading(dialog, loading, message = "") {
  const content = dialog.querySelector("#article-preview-content");
  const status = dialog.querySelector("[data-article-preview-status]");
  content?.toggleAttribute("aria-busy", loading);
  if (!(status instanceof HTMLElement)) return;
  status.textContent = message;
  status.hidden = !message;
  status.setAttribute("role", "status");
}

function showNetworkError(dialog, source, statusCode) {
  setLoading(dialog, false);
  const status = dialog.querySelector("[data-article-preview-status]");
  if (status instanceof HTMLElement) {
    status.textContent =
      statusCode === 401 || statusCode === 403
        ? "登录状态或访问权限已失效。"
        : "文章内容加载失败，请重试。";
    status.hidden = false;
    status.setAttribute("role", "alert");
  }
  if (source?.matches?.("[data-article-preview-trigger]")) {
    const content = dialog.querySelector("#article-preview-content");
    if (content instanceof HTMLElement && !content.hasChildNodes()) {
      const message = document.createElement("p");
      message.className = "admin-article-preview__request-error";
      message.textContent = "暂时无法读取这篇文章。";
      content.append(message);
    }
  }
}

function bindPreviewEvents() {
  if (previewEventsBound) return;
  previewEventsBound = true;

  document.addEventListener("htmx:beforeRequest", (event) => {
    const source = previewSource(event);
    const dialog = previewDialog();
    if (!(source instanceof HTMLElement) || !dialog) return;
    const initial = source.matches("[data-article-preview-trigger]");
    dialog.dataset.previewRequestKind = initial ? "initial" : "version";
    if (initial) {
      if (source.id) dialog.dataset.dialogReturnFocus = source.id;
      dialog.dataset.dialogReturnUrl = `${location.pathname}${location.search}${location.hash}`;
      dialog.querySelector("#article-preview-content")?.replaceChildren();
      if (!dialog.open) dialog.showModal();
    }
    setLoading(dialog, true, "正在加载文章内容");
  });

  document.addEventListener("htmx:afterSwap", (event) => {
    const target = event.detail?.target;
    const dialog = previewDialog();
    if (!(target instanceof HTMLElement) || target.id !== "article-preview-content") {
      return;
    }
    if (!dialog) return;
    setLoading(dialog, false);
    const focusTarget =
      dialog.dataset.previewRequestKind === "version"
        ? target.querySelector("select[name='revision_id']")
        : target.querySelector("[data-article-preview-title]");
    delete dialog.dataset.previewRequestKind;
    if (focusTarget instanceof HTMLElement) {
      requestAnimationFrame(() => focusTarget.focus({ preventScroll: true }));
    }
  });

  const handleRequestError = (event) => {
    const source = previewSource(event);
    const dialog = previewDialog();
    if (!(source instanceof HTMLElement) || !dialog) return;
    showNetworkError(dialog, source, event.detail?.xhr?.status ?? 0);
  };
  document.addEventListener("htmx:sendError", handleRequestError);
  document.addEventListener("htmx:responseError", handleRequestError);
  document.addEventListener("htmx:timeout", handleRequestError);
}

export function initializeAdministrationArticlePreviews(root = document) {
  bindPreviewEvents();
  root
    .querySelectorAll?.("[data-admin-article-preview-dialog]")
    .forEach((dialog) => {
      if (!(dialog instanceof HTMLDialogElement) || dialog.dataset.previewBound) {
        return;
      }
      dialog.dataset.previewBound = "true";
      dialog.addEventListener("click", (event) => {
        if (event.target === dialog) dialog.close("cancel");
      });
      dialog.addEventListener("close", () => {
        setLoading(dialog, false);
        dialog.querySelector("#article-preview-content")?.replaceChildren();
        delete dialog.dataset.previewRequestKind;
      });
    });
}
