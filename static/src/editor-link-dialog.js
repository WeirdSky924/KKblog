import {
  ExternalLink,
  Link as LinkIcon,
  Unlink,
  X,
  createIcons,
} from "lucide";

const CONTROL_CHARACTER = /\p{Cc}/u;
const SCHEME = /^([a-z][a-z0-9+.-]*):/i;

function invalid(message) {
  return { valid: false, message };
}

export function validateEditorLinkHref(value) {
  if (typeof value !== "string" || !value) {
    return invalid("请输入链接地址。");
  }
  if (value !== value.trim()) {
    return invalid("链接地址前后不能有空格。");
  }
  if (CONTROL_CHARACTER.test(value) || value.startsWith("//") || value.startsWith("\\")) {
    return invalid("请输入安全的站内地址、HTTP(S) 或邮箱链接。");
  }

  const matched = value.match(SCHEME);
  if (!matched) return { valid: true, value };
  const scheme = matched[1].toLowerCase();
  if (scheme === "mailto") {
    const address = value.slice(matched[0].length);
    return address && !address.startsWith("//")
      ? { valid: true, value }
      : invalid("请输入完整的邮箱链接。");
  }
  if (scheme !== "http" && scheme !== "https") {
    return invalid("链接只支持站内地址、HTTP(S) 或 mailto。");
  }

  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    return invalid("链接地址格式不正确。");
  }
  const authority = value.slice(value.indexOf("//") + 2).split(/[/?#]/, 1)[0];
  const bracketEnd = authority.startsWith("[") ? authority.indexOf("]") : -1;
  const explicitPort =
    bracketEnd >= 0 ? authority.slice(bracketEnd + 1).startsWith(":") : authority.includes(":");
  if (
    !parsed.hostname ||
    parsed.username ||
    parsed.password ||
    parsed.port ||
    authority.includes("@") ||
    explicitPort
  ) {
    return invalid("链接不能包含账号、密码或显式端口。");
  }
  return { valid: true, value };
}

export const EDITOR_LINK_OPTIONS = Object.freeze({
  isAllowedUri: (href) => validateEditorLinkHref(href).valid,
  shouldAutoLink: (href) => validateEditorLinkHref(href).valid,
});

function element(tag, { className, text, attributes = {} } = {}) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  Object.entries(attributes).forEach(([name, value]) => node.setAttribute(name, value));
  return node;
}

function actionButton(label, icon, className = "button button--secondary") {
  const button = element("button", {
    className,
    attributes: { type: "button" },
  });
  const iconNode = element("i", { attributes: { "data-lucide": icon } });
  button.append(iconNode, element("span", { text: label }));
  return button;
}

export function initializeEditorLinkDialog({ root, editor }) {
  const host = root.closest("#author-editor-workspace") || document.body;
  const dialog = element("dialog", {
    className: "author-link-dialog",
    attributes: {
      "aria-labelledby": "author-link-dialog-title",
      "aria-describedby": "author-link-dialog-error",
    },
  });
  dialog.dataset.editorLinkDialog = "";

  const form = element("form", { attributes: { method: "dialog" } });
  const header = element("header");
  const heading = element("h3", {
    text: "链接",
    attributes: { id: "author-link-dialog-title" },
  });
  const closeButton = element("button", {
    className: "author-link-dialog__close",
    attributes: { type: "button", "aria-label": "关闭链接设置", title: "关闭" },
  });
  closeButton.append(element("i", { attributes: { "data-lucide": "x" } }));
  header.append(heading, closeButton);

  const hrefLabel = element("label", { text: "链接地址" });
  const hrefInput = element("input", {
    attributes: {
      type: "text",
      inputmode: "url",
      autocomplete: "url",
      required: "",
      placeholder: "https://example.com 或 /站内路径",
    },
  });
  hrefLabel.append(hrefInput);
  const titleLabel = element("label", { text: "链接标题（可选）" });
  const titleInput = element("input", {
    attributes: { type: "text", autocomplete: "off" },
  });
  titleLabel.append(titleInput);
  const error = element("p", {
    className: "author-link-dialog__error",
    attributes: { id: "author-link-dialog-error", role: "alert" },
  });
  error.hidden = true;

  const actions = element("div", { className: "author-link-dialog__actions" });
  const contextual = element("div");
  const removeButton = actionButton("移除链接", "unlink");
  const openLink = element("a", {
    className: "button button--secondary",
    attributes: {
      target: "_blank",
      rel: "noopener noreferrer",
      title: "在新标签页打开当前链接",
    },
  });
  openLink.append(
    element("i", { attributes: { "data-lucide": "external-link" } }),
    element("span", { text: "打开链接" }),
  );
  contextual.append(removeButton, openLink);
  const decisions = element("div");
  const cancelButton = actionButton("取消", "x");
  const applyButton = actionButton("应用链接", "link", "button button--primary");
  applyButton.type = "submit";
  decisions.append(cancelButton, applyButton);
  actions.append(contextual, decisions);
  form.append(header, hrefLabel, titleLabel, error, actions);
  dialog.append(form);
  host.append(dialog);

  createIcons({
    root: dialog,
    icons: { ExternalLink, Link: LinkIcon, Unlink, X },
    attrs: { "aria-hidden": "true", focusable: "false", width: "20", height: "20" },
  });

  let returnFocus = null;
  let range = null;

  const clearError = () => {
    error.hidden = true;
    error.textContent = "";
    hrefInput.removeAttribute("aria-invalid");
  };
  const showError = (message) => {
    error.textContent = message;
    error.hidden = false;
    hrefInput.setAttribute("aria-invalid", "true");
    hrefInput.focus();
  };
  const restoreSelection = () => {
    if (!range) return null;
    return editor.chain().focus().setTextSelection(range);
  };
  const close = (value = "cancel") => {
    if (dialog.open) dialog.close(value);
  };

  const open = (trigger) => {
    const active = editor.isActive("link");
    if (editor.state.selection.empty && !active) return false;
    if (active) editor.chain().focus().extendMarkRange("link").run();
    range = {
      from: editor.state.selection.from,
      to: editor.state.selection.to,
    };
    const attributes = active ? editor.getAttributes("link") : {};
    hrefInput.value = attributes.href || "";
    titleInput.value = attributes.title || "";
    removeButton.hidden = !active;
    const validated = validateEditorLinkHref(attributes.href || "");
    openLink.hidden = !active || !validated.valid;
    if (!openLink.hidden) openLink.href = validated.value;
    else openLink.removeAttribute("href");
    returnFocus = trigger instanceof HTMLElement ? trigger : null;
    clearError();
    if (!dialog.open) dialog.showModal();
    hrefInput.focus();
    hrefInput.select();
    return true;
  };

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const validated = validateEditorLinkHref(hrefInput.value);
    if (!validated.valid) {
      showError(validated.message);
      return;
    }
    const chain = restoreSelection();
    if (!chain?.setLink({ href: validated.value, title: titleInput.value || null }).run()) {
      showError("无法应用链接，请重新选择文字后再试。");
      return;
    }
    close("apply");
  });
  removeButton.addEventListener("click", () => {
    if (restoreSelection()?.unsetLink().run()) close("remove");
  });
  closeButton.addEventListener("click", () => close());
  cancelButton.addEventListener("click", () => close());
  dialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    close();
  });
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) close();
  });
  dialog.addEventListener("close", () => {
    clearError();
    const target = returnFocus;
    returnFocus = null;
    if (target?.isConnected) {
      requestAnimationFrame(() => {
        const details = target.closest("details");
        const disclosure = details?.querySelector(":scope > summary");
        const focusTarget = details && !details.open ? disclosure : target;
        if (focusTarget instanceof HTMLElement && focusTarget.isConnected) {
          focusTarget.focus({ preventScroll: true });
        }
      });
    }
  });

  return {
    open,
    dispose() {
      if (dialog.open) dialog.close();
      dialog.remove();
    },
  };
}
