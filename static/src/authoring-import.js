const CONFIRM_MESSAGE = "已选择的导入文件尚未解析，离开会清除这个选择。确定离开吗？";

function pendingImportForm() {
  const form = document.querySelector("[data-import-upload-form]");
  if (!(form instanceof HTMLFormElement)) return null;
  const input = form.querySelector("input[type='file']");
  if (!(input instanceof HTMLInputElement) || !input.files?.length) return null;
  if (form.dataset.submitting === "true" || form.dataset.importLeaving === "true") {
    return null;
  }
  return form;
}

function initializeImportLeaveGuard() {
  if (document.documentElement.dataset.importLeaveGuard === "true") return;
  document.documentElement.dataset.importLeaveGuard = "true";

  window.addEventListener("beforeunload", (event) => {
    if (!pendingImportForm()) return;
    event.preventDefault();
    event.returnValue = "";
  });
  document.addEventListener(
    "click",
    (event) => {
      const link = event.target instanceof Element ? event.target.closest("a[href]") : null;
      const form = pendingImportForm();
      if (!(link instanceof HTMLAnchorElement) || !form) return;
      if (!window.confirm(CONFIRM_MESSAGE)) {
        event.preventDefault();
        event.stopImmediatePropagation();
        return;
      }
      form.dataset.importLeaving = "true";
    },
    true,
  );
}

export function initializeImportUploadForms(root = document) {
  initializeImportLeaveGuard();
  root.querySelectorAll("[data-import-upload-form]").forEach((form) => {
    if (!(form instanceof HTMLFormElement) || form.dataset.importReady === "true") {
      return;
    }
    const input = form.querySelector("input[type='file']");
    if (!(input instanceof HTMLInputElement)) return;

    form.dataset.importReady = "true";
    form.addEventListener(
      "submit",
      () => {
        form.dataset.importLeaving = "true";
      },
      { once: true },
    );
  });
}
