import { Node as TipTapNode } from "@tiptap/core";
import { Plugin } from "@tiptap/pm/state";
import { Download, Paperclip, Trash2, createIcons } from "lucide";

import { dispatchIsolatedEditorTransaction } from "./editor-history.js";
import { AUTHOR_MEDIA_SOURCE } from "./editor-image.js";

const TYPE_LABELS = Object.freeze({
  "application/zip": "ZIP",
  "application/x-7z-compressed": "7z",
  "application/vnd.rar": "RAR",
  "text/markdown": "Markdown",
  "text/plain": "TXT",
});

export function normalizeAuthorAttachmentAttributes(attributes) {
  const source = typeof attributes?.src === "string" ? attributes.src : "";
  return source ? { src: source } : {};
}

function attachmentNodes(document) {
  const root = typeof document?.toJSON === "function" ? document.toJSON() : document;
  const nodes = [];
  const visit = (node) => {
    if (!node || typeof node !== "object") return;
    if (node.type === "attachment") nodes.push(node);
    for (const child of node.content || []) visit(child);
  };
  visit(root);
  return nodes;
}

export function authorAttachmentDocumentWithinLimits(document) {
  const nodes = attachmentNodes(document);
  return (
    nodes.length <= 1 &&
    nodes.every((node) =>
      AUTHOR_MEDIA_SOURCE.test(String(node.attrs?.src || "")),
    )
  );
}

function announceLimit() {
  document.dispatchEvent(
    new CustomEvent("kaj:feedback", {
      detail: {
        key: "author-attachment-limit",
        level: "error",
        message: "一篇文章只能插入一个已授权附件。",
        timeout: 5500,
      },
    }),
  );
}

function announceAttachment(message, level) {
  document.dispatchEvent(
    new CustomEvent("kaj:feedback", {
      detail: {
        key: "author-attachment-card",
        level,
        message,
        timeout: level === "error" ? 6500 : 4500,
      },
    }),
  );
}

function formatSize(value) {
  const size = Number(value);
  if (!Number.isFinite(size) || size < 0) return "";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KiB`;
  return `${(size / 1024 / 1024).toFixed(1)} MiB`;
}

function attachmentMetadata(getMetadata, mediaId) {
  const value = typeof getMetadata === "function" ? getMetadata(mediaId) : null;
  if (!value || typeof value !== "object") return null;
  const name = typeof value.name === "string" && value.name ? value.name : "文章附件";
  const mime = TYPE_LABELS[value.mime] || "附件";
  const size = formatSize(value.size);
  return { name, detail: size ? `${mime} · ${size}` : mime };
}

function mediaIdFromSource(value) {
  return String(value || "").match(AUTHOR_MEDIA_SOURCE)?.[1] || "";
}

function attachmentCard({ mediaId, metadata, editable = false }) {
  const dom = document.createElement("aside");
  dom.className = editable ? "author-attachment-block" : "article-attachment-card";
  dom.dataset.authorAttachmentId = mediaId;
  dom.contentEditable = "false";
  const icon = document.createElement("i");
  icon.dataset.lucide = "paperclip";
  const copy = document.createElement("div");
  const name = document.createElement("strong");
  name.textContent = metadata?.name || "文章附件";
  const detail = document.createElement("span");
  detail.textContent = metadata?.detail || "可下载文件";
  copy.append(name, detail);
  const download = document.createElement("a");
  download.className = "button button--secondary";
  download.href = mediaId ? `/_kaj/media/${mediaId}` : "";
  download.download = metadata?.name || "";
  download.setAttribute("aria-label", `下载 ${metadata?.name || "文章附件"}`);
  const downloadIcon = document.createElement("i");
  downloadIcon.dataset.lucide = "download";
  const downloadLabel = document.createElement("span");
  downloadLabel.textContent = "下载";
  download.append(downloadIcon, downloadLabel);
  dom.append(icon, copy, download);
  return dom;
}

const AuthorAttachment = TipTapNode.create({
  name: "attachment",
  group: "block",
  atom: true,
  draggable: true,
  selectable: true,
  addOptions() {
    return { getMetadata: null, announce: null };
  },
  addAttributes() {
    return {
      src: {
        default: null,
        parseHTML: (element) => {
          const mediaId = element.getAttribute("data-author-attachment-id") || "";
          return AUTHOR_MEDIA_SOURCE.test(`media:${mediaId}`)
            ? `media:${mediaId}`
            : null;
        },
      },
    };
  },
  parseHTML() {
    return [{ tag: "aside[data-author-attachment-id]" }];
  },
  renderHTML({ HTMLAttributes }) {
    const mediaId = mediaIdFromSource(HTMLAttributes.src);
    return [
      "aside",
      { "data-author-attachment-id": mediaId },
      ["strong", {}, "文章附件"],
      ["span", {}, "可下载文件"],
      ["a", { href: mediaId ? `/_kaj/media/${mediaId}` : "", download: "" }, "下载"],
    ];
  },
  addProseMirrorPlugins() {
    return [
      new Plugin({
        filterTransaction(transaction) {
          if (
            !transaction.docChanged ||
            authorAttachmentDocumentWithinLimits(transaction.doc)
          ) {
            return true;
          }
          announceLimit();
          return false;
        },
      }),
    ];
  },
  addNodeView() {
    return ({ node, editor, getPos }) => {
      let currentNode = node;
      let mediaId = mediaIdFromSource(node.attrs.src);
      let metadata = attachmentMetadata(this.options.getMetadata, mediaId);
      const dom = attachmentCard({ mediaId, metadata, editable: true });
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "icon-button author-attachment-block__remove";
      remove.setAttribute("aria-label", "从正文移除附件卡片");
      remove.title = "从正文移除附件卡片";
      const removeIcon = document.createElement("i");
      removeIcon.dataset.lucide = "trash-2";
      remove.append(removeIcon);
      dom.append(remove);
      createIcons({
        root: dom,
        icons: { Download, Paperclip, Trash2 },
        attrs: { "aria-hidden": "true", focusable: "false" },
      });

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
        (this.options.announce || announceAttachment)(
          "附件卡片已从正文移除，文章附件仍会保留。",
          "success",
        );
      };
      remove.addEventListener("click", removeNode);

      return {
        dom,
        update: (nextNode) => {
          if (nextNode.type !== currentNode.type) return false;
          currentNode = nextNode;
          const nextMediaId = mediaIdFromSource(nextNode.attrs.src);
          const nextMetadata = attachmentMetadata(
            this.options.getMetadata,
            nextMediaId,
          );
          if (nextMediaId !== mediaId || nextMetadata?.name !== metadata?.name) {
            return false;
          }
          mediaId = nextMediaId;
          metadata = nextMetadata;
          return true;
        },
        selectNode: () => dom.setAttribute("data-selected", "true"),
        deselectNode: () => dom.removeAttribute("data-selected"),
        stopEvent: (event) =>
          event.target instanceof Element &&
          event.target.closest("a, button") !== null,
        ignoreMutation: () => true,
        destroy: () => remove.removeEventListener("click", removeNode),
      };
    };
  },
});

export function createAuthorAttachmentExtension(options = {}) {
  return Object.keys(options).length ? AuthorAttachment.configure(options) : AuthorAttachment;
}

export function upsertAuthorAttachment(editor, assetId) {
  const source = `media:${assetId}`;
  if (!AUTHOR_MEDIA_SOURCE.test(source)) return false;
  let existing = null;
  editor.state.doc.descendants((node, position) => {
    if (!existing && node.type.name === "attachment") existing = { node, position };
  });
  if (!existing) {
    return editor.chain().focus().insertContent({ type: "attachment", attrs: { src: source } }).run();
  }
  if (existing.node.attrs.src === source) {
    return editor.chain().focus().setNodeSelection(existing.position).run();
  }
  return dispatchIsolatedEditorTransaction(
    editor,
    editor.state.tr.setNodeMarkup(existing.position, undefined, { src: source }),
    { focus: true },
  );
}

export function removeAuthorAttachment(editor) {
  const positions = [];
  editor.state.doc.descendants((node, position) => {
    if (node.type.name === "attachment") positions.push({ position, size: node.nodeSize });
  });
  if (!positions.length) return false;
  const transaction = editor.state.tr;
  positions.reverse().forEach(({ position, size }) =>
    transaction.delete(position, position + size),
  );
  return dispatchIsolatedEditorTransaction(editor, transaction);
}
