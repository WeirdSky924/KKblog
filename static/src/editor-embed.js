import { Node as TipTapNode } from "@tiptap/core";
import {
  ExternalLink,
  Pencil,
  SquarePlay,
  Trash2,
  X,
  createIcons,
} from "lucide";

import { dispatchIsolatedEditorTransaction } from "./editor-history.js";

const CONTROL_CHARACTER = /\p{Cc}/u;
const BILIBILI_PATH = /^\/video\/(BV[A-Za-z0-9]{10,20})\/?$/;
const SOURCE_LABELS = Object.freeze({ bilibili: "Bilibili" });

function enabledSourceList(values) {
  if (!Array.isArray(values)) return [];
  return [...new Set(values
    .filter((value) => typeof value === "string")
    .map((value) => value.toLowerCase())
    .filter((value) => Object.hasOwn(SOURCE_LABELS, value)))]
    .sort();
}

function invalid(message) {
  return { valid: false, message };
}

function projectKnownEmbed(source, value) {
  if (source !== "bilibili" || typeof value !== "string" || !value) return null;
  if (value !== value.trim() || CONTROL_CHARACTER.test(value) || value.startsWith("//")) {
    return null;
  }
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    return null;
  }
  const authority = value.slice(value.indexOf("//") + 2).split(/[/?#]/, 1)[0];
  if (
    parsed.protocol !== "https:" ||
    parsed.hostname !== "www.bilibili.com" ||
    parsed.username ||
    parsed.password ||
    parsed.port ||
    authority.includes("@") ||
    authority.includes(":") ||
    parsed.search ||
    parsed.hash
  ) {
    return null;
  }
  const match = parsed.pathname.match(BILIBILI_PATH);
  if (!match) return null;
  return {
    source,
    url: `https://www.bilibili.com/video/${match[1]}`,
    resourceId: match[1],
  };
}

export function validateAuthorEmbedUrl(sourceValue, url, enabledSources) {
  const source = typeof sourceValue === "string" ? sourceValue.toLowerCase() : "";
  if (!enabledSourceList(enabledSources).includes(source)) {
    return invalid("当前来源未启用。");
  }
  const projection = projectKnownEmbed(source, url);
  return projection
    ? { valid: true, ...projection }
    : invalid("请输入标准的 Bilibili 视频地址。");
}

export function normalizeAuthorEmbedAttributes(attributes) {
  const source = typeof attributes?.source === "string"
    ? attributes.source.toLowerCase()
    : "";
  const url = typeof attributes?.url === "string" ? attributes.url : "";
  return { source, url };
}

function iconButton(label, icon) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "icon-button";
  button.setAttribute("aria-label", label);
  button.title = label;
  const iconNode = document.createElement("i");
  iconNode.dataset.lucide = icon;
  button.append(iconNode);
  return button;
}

function createEmbedCard(attributes, enabledSources) {
  const normalized = normalizeAuthorEmbedAttributes(attributes);
  const projection = projectKnownEmbed(normalized.source, normalized.url);
  const enabled = enabledSourceList(enabledSources).includes(normalized.source);
  const card = document.createElement("aside");
  card.className = "author-embed-block";
  card.contentEditable = "false";
  card.dataset.authorEmbedSource = normalized.source;

  const icon = document.createElement("i");
  icon.dataset.lucide = "square-play";
  const copy = document.createElement("div");
  const name = document.createElement("strong");
  name.textContent = projection ? SOURCE_LABELS[projection.source] : "嵌入内容";
  const detail = document.createElement("span");
  detail.textContent = projection
    ? `${projection.resourceId}${enabled ? "" : " · 来源已停用"}`
    : "来源不可用";
  copy.append(name, detail);
  const actions = document.createElement("div");
  actions.className = "author-embed-block__actions";
  if (projection) {
    const open = document.createElement("a");
    open.className = "icon-button";
    open.href = projection.url;
    open.target = "_blank";
    open.rel = "noopener noreferrer";
    open.setAttribute("aria-label", "在 Bilibili 打开");
    open.title = "在 Bilibili 打开";
    const openIcon = document.createElement("i");
    openIcon.dataset.lucide = "external-link";
    open.append(openIcon);
    actions.append(open);
  }
  card.append(icon, copy, actions);
  return { card, actions, enabled };
}

const AuthorEmbed = TipTapNode.create({
  name: "embed",
  group: "block",
  atom: true,
  draggable: true,
  selectable: true,
  addOptions() {
    return { enabledSources: [], openDialog: null };
  },
  addStorage() {
    return { enabledSources: enabledSourceList(this.options.enabledSources) };
  },
  addAttributes() {
    return {
      source: {
        default: null,
        parseHTML: (element) =>
          element.getAttribute("data-author-embed-source"),
      },
      url: {
        default: null,
        parseHTML: (element) => element.getAttribute("data-author-embed-url"),
      },
    };
  },
  parseHTML() {
    return [{ tag: "aside[data-author-embed-source]" }];
  },
  renderHTML({ HTMLAttributes }) {
    const attributes = normalizeAuthorEmbedAttributes(HTMLAttributes);
    return [
      "aside",
      {
        "data-author-embed-source": attributes.source,
        "data-author-embed-url": attributes.url,
      },
      ["strong", {}, SOURCE_LABELS[attributes.source] || "嵌入内容"],
    ];
  },
  addNodeView() {
    return ({ node, editor, getPos }) => {
      let currentNode = node;
      const { card, actions, enabled } = createEmbedCard(
        node.attrs,
        this.options.enabledSources,
      );
      const edit = iconButton("编辑嵌入内容", "pencil");
      edit.hidden = !enabled;
      const remove = iconButton("移除嵌入内容", "trash-2");
      actions.append(edit, remove);
      createIcons({
        root: card,
        icons: { ExternalLink, Pencil, SquarePlay, Trash2 },
        attrs: { "aria-hidden": "true", focusable: "false" },
      });

      const editNode = () => {
        const position = getPos();
        if (!Number.isInteger(position)) return;
        this.options.openDialog?.({ trigger: edit, position });
      };
      const removeNode = () => {
        const position = getPos();
        if (!Number.isInteger(position)) return;
        const selected = editor.state.doc.nodeAt(position);
        if (selected?.type !== currentNode.type) return;
        dispatchIsolatedEditorTransaction(
          editor,
          editor.state.tr.delete(position, position + selected.nodeSize),
          { focus: true },
        );
      };
      edit.addEventListener("click", editNode);
      remove.addEventListener("click", removeNode);
      return {
        dom: card,
        update(nextNode) {
          if (nextNode.type !== currentNode.type) return false;
          const changed = JSON.stringify(nextNode.attrs) !== JSON.stringify(currentNode.attrs);
          currentNode = nextNode;
          return !changed;
        },
        selectNode: () => card.setAttribute("data-selected", "true"),
        deselectNode: () => card.removeAttribute("data-selected"),
        stopEvent: (event) => event.target instanceof Element && Boolean(event.target.closest("a, button")),
        ignoreMutation: () => true,
        destroy() {
          edit.removeEventListener("click", editNode);
          remove.removeEventListener("click", removeNode);
        },
      };
    };
  },
});

export function createAuthorEmbedExtension(options = {}) {
  return AuthorEmbed.configure({
    ...options,
    enabledSources: enabledSourceList(options.enabledSources),
  });
}

function field(labelText, control) {
  const label = document.createElement("label");
  label.append(document.createTextNode(labelText), control);
  return label;
}

function restoreBookmark(editor, bookmark) {
  if (!bookmark) return;
  try {
    const selection = bookmark.resolve(editor.state.doc);
    editor.view.dispatch(
      editor.state.tr.setSelection(selection).setMeta("addToHistory", false),
    );
  } catch {
    // The current valid selection is safer than guessing after a document change.
  }
}

export function initializeEditorEmbedDialog({ root, editor, enabledSources }) {
  const sources = enabledSourceList(enabledSources);
  const host = root.closest("#author-editor-workspace") || document.body;
  const dialog = document.createElement("dialog");
  dialog.className = "author-embed-dialog";
  dialog.setAttribute("aria-labelledby", "author-embed-dialog-title");
  dialog.setAttribute("aria-describedby", "author-embed-dialog-error");
  dialog.dataset.editorEmbedDialog = "";
  const form = document.createElement("form");
  form.method = "dialog";
  const header = document.createElement("header");
  const heading = document.createElement("h3");
  heading.id = "author-embed-dialog-title";
  heading.textContent = "嵌入内容";
  const closeButton = iconButton("关闭嵌入设置", "x");
  closeButton.classList.add("author-embed-dialog__close");
  header.append(heading, closeButton);

  const sourceSelect = document.createElement("select");
  sourceSelect.required = true;
  sourceSelect.setAttribute("aria-label", "内容来源");
  sources.forEach((source) => {
    const option = document.createElement("option");
    option.value = source;
    option.textContent = SOURCE_LABELS[source];
    sourceSelect.append(option);
  });
  const urlInput = document.createElement("input");
  urlInput.type = "url";
  urlInput.required = true;
  urlInput.autocomplete = "url";
  urlInput.inputMode = "url";
  urlInput.placeholder = "https://www.bilibili.com/video/BV...";
  const error = document.createElement("p");
  error.id = "author-embed-dialog-error";
  error.className = "author-embed-dialog__error";
  error.setAttribute("role", "alert");
  error.hidden = true;
  const actions = document.createElement("div");
  actions.className = "author-embed-dialog__actions";
  const removeButton = document.createElement("button");
  removeButton.type = "button";
  removeButton.className = "button button--secondary";
  removeButton.textContent = "移除";
  const decisions = document.createElement("div");
  const cancelButton = document.createElement("button");
  cancelButton.type = "button";
  cancelButton.className = "button button--secondary";
  cancelButton.textContent = "取消";
  const applyButton = document.createElement("button");
  applyButton.type = "submit";
  applyButton.className = "button button--primary";
  applyButton.textContent = "应用";
  decisions.append(cancelButton, applyButton);
  actions.append(removeButton, decisions);
  form.append(
    header,
    field("来源", sourceSelect),
    field("视频地址", urlInput),
    error,
    actions,
  );
  dialog.append(form);
  host.append(dialog);
  createIcons({
    root: dialog,
    icons: { X },
    attrs: { "aria-hidden": "true", focusable: "false" },
  });

  let returnFocus = null;
  let bookmark = null;
  let editingPosition = null;
  let restoreOnClose = false;
  const clearError = () => {
    error.hidden = true;
    error.textContent = "";
    urlInput.removeAttribute("aria-invalid");
  };
  const showError = (message) => {
    error.textContent = message;
    error.hidden = false;
    urlInput.setAttribute("aria-invalid", "true");
    urlInput.focus();
  };
  const close = (value = "cancel") => {
    if (dialog.open) dialog.close(value);
  };
  const open = ({ trigger = null, position = null } = {}) => {
    if (!sources.length) return false;
    const node = Number.isInteger(position) ? editor.state.doc.nodeAt(position) : null;
    if (node && node.type.name !== "embed") return false;
    returnFocus = trigger instanceof HTMLElement ? trigger : null;
    bookmark = editor.state.selection.getBookmark();
    editingPosition = node ? position : null;
    restoreOnClose = true;
    const attrs = normalizeAuthorEmbedAttributes(node?.attrs);
    sourceSelect.value = sources.includes(attrs.source) ? attrs.source : sources[0];
    urlInput.value = attrs.url || "";
    removeButton.hidden = !node;
    clearError();
    if (!dialog.open) dialog.showModal();
    urlInput.focus();
    urlInput.select();
    return true;
  };

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const validated = validateAuthorEmbedUrl(
      sourceSelect.value,
      urlInput.value,
      sources,
    );
    if (!validated.valid) {
      showError(validated.message);
      return;
    }
    let transaction = editor.state.tr;
    if (Number.isInteger(editingPosition)) {
      const node = editor.state.doc.nodeAt(editingPosition);
      if (node?.type.name !== "embed") {
        showError("嵌入内容已发生变化，请关闭后重试。");
        return;
      }
      transaction = transaction.setNodeMarkup(editingPosition, undefined, {
        source: validated.source,
        url: validated.url,
      });
    } else {
      restoreBookmark(editor, bookmark);
      const node = editor.state.schema.nodes.embed.create({
        source: validated.source,
        url: validated.url,
      });
      transaction = editor.state.tr.replaceSelectionWith(node);
    }
    restoreOnClose = false;
    dispatchIsolatedEditorTransaction(editor, transaction, { focus: true });
    close("apply");
  });
  removeButton.addEventListener("click", () => {
    if (!Number.isInteger(editingPosition)) return;
    const node = editor.state.doc.nodeAt(editingPosition);
    if (node?.type.name !== "embed") return;
    restoreOnClose = false;
    dispatchIsolatedEditorTransaction(
      editor,
      editor.state.tr.delete(editingPosition, editingPosition + node.nodeSize),
      { focus: true },
    );
    close("remove");
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
    if (restoreOnClose) restoreBookmark(editor, bookmark);
    const target = returnFocus;
    restoreOnClose = false;
    bookmark = null;
    returnFocus = null;
    editingPosition = null;
    requestAnimationFrame(() => {
      if (target?.isConnected) {
        const details = target.closest("details");
        const disclosure = details?.querySelector(":scope > summary");
        const focusTarget = details && !details.open ? disclosure : target;
        if (focusTarget instanceof HTMLElement && focusTarget.isConnected) {
          focusTarget.focus({ preventScroll: true });
          return;
        }
      }
      editor.commands.focus();
    });
  });

  return {
    open,
    dispose() {
      if (dialog.open) dialog.close();
      dialog.remove();
    },
  };
}
