const RESET_TOKEN_PATTERN = /^[0-9a-f-]{36}\.[A-Za-z0-9_-]{32,128}$/i;

export function initializeAdminPasswordResetLink(root = document) {
  root.querySelectorAll("[data-admin-password-reset]").forEach((page) => {
    if (page.dataset.adminPasswordResetReady === "true") return;
    page.dataset.adminPasswordResetReady = "true";

    const form = page.querySelector("[data-admin-password-reset-form]");
    const tokenField = form?.querySelector("input[name='token']");
    const status = page.querySelector("[data-reset-link-status]");
    const submit = form?.querySelector("button[type='submit']");
    if (!(form instanceof HTMLFormElement) || !(tokenField instanceof HTMLInputElement)) {
      return;
    }

    const fragmentToken = window.location.hash.slice(1);
    if (fragmentToken) {
      window.history.replaceState(
        window.history.state,
        document.title,
        `${window.location.pathname}${window.location.search}`,
      );
    }
    const token = fragmentToken || tokenField.value;
    if (!RESET_TOKEN_PATTERN.test(token)) {
      if (status) {
        status.textContent = "请使用管理员邮件中的有效链接打开此页面。";
      }
      return;
    }

    tokenField.value = token;
    form.hidden = false;
    if (submit instanceof HTMLButtonElement) submit.disabled = false;
    if (status) status.hidden = true;
    form.querySelector("input[name='new_password']")?.focus({ preventScroll: true });
  });
}
