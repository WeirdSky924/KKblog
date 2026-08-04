import { Editor, Node, mergeAttributes } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";

import { initializeLocalDraft } from "./authoring-local-draft.js";
import {
  MarkdownFileImportError,
  readMarkdownFile,
} from "./markdown-file-import.js";

const MEDIA_SOURCE = /^media:([0-9A-HJKMNP-TV-Z]{26})$/;
const activeEditors = new WeakMap();

const AuthorImage = Node.create({
  name: "image",
  group: "block",
  atom: true,
  draggable: true,
  addAttributes() {
    return {
      src: { default: null },
      alt: { default: null },
      title: { default: null },
    };
  },
  parseHTML() {
    return [{ tag: "img[data-author-media-id]" }];
  },
  renderHTML({ HTMLAttributes }) {
    const matched = String(HTMLAttributes.src || "").match(MEDIA_SOURCE);
    const mediaId = matched?.[1] || "";
    const source = mediaId ? `/_kaj/media/${mediaId}` : "";
    return [
      "img",
      mergeAttributes(HTMLAttributes, {
        src: source,
        "data-author-media-id": mediaId,
      }),
    ];
  },
});

function normalizeTiptap(value) {
  if (Array.isArray(value)) {
    return value.map(normalizeTiptap);
  }
  if (!value || typeof value !== "object") {
    return value;
  }
  const normalized = {};
  Object.entries(value).forEach(([key, item]) => {
    if (item === null || item === undefined) {
      return;
    }
    if (key === "attrs" && value.type === "image") {
      normalized.attrs = Object.fromEntries(
        ["src", "alt", "title"]
          .filter((name) => typeof item[name] === "string" && item[name])
          .map((name) => [name, item[name]]),
      );
      return;
    }
    if (key === "attrs" && value.type === "link") {
      normalized.attrs = Object.fromEntries(
        ["href", "title"]
          .filter((name) => typeof item[name] === "string" && item[name])
          .map((name) => [name, item[name]]),
      );
      return;
    }
    normalized[key] = normalizeTiptap(item);
  });
  return normalized;
}

function sourceMetrics(format, source) {
  const bytes = new TextEncoder().encode(source).length;
  if (format === "MARKDOWN") {
    const media = source.match(/!\[[^\]]*\]\(media:[0-9A-HJKMNP-TV-Z]{26}\)/g) || [];
    const text = source.replaceAll(/!\[[^\]]*\]\(media:[0-9A-HJKMNP-TV-Z]{26}\)/g, "");
    return { bytes, characters: text.trim().length, media: media.length };
  }
  try {
    const document = JSON.parse(source);
    let characters = 0;
    let media = 0;
    const stack = [document];
    while (stack.length) {
      const node = stack.pop();
      if (!node || typeof node !== "object") continue;
      if (node.type === "text" && typeof node.text === "string") {
        characters += node.text.length;
      }
      if (node.type === "image") media += 1;
      if (Array.isArray(node.content)) stack.push(...node.content);
    }
    return { bytes, characters, media };
  } catch {
    return { bytes, characters: 0, media: 0 };
  }
}

function commandFor(editor, name) {
  const chain = editor.chain().focus();
  return {
    bold: () => chain.toggleBold().run(),
    italic: () => chain.toggleItalic().run(),
    strike: () => chain.toggleStrike().run(),
    heading: () => chain.toggleHeading({ level: 2 }).run(),
    bulletList: () => chain.toggleBulletList().run(),
    orderedList: () => chain.toggleOrderedList().run(),
    blockquote: () => chain.toggleBlockquote().run(),
    codeBlock: () => chain.toggleCodeBlock().run(),
    undo: () => chain.undo().run(),
    redo: () => chain.redo().run(),
  }[name];
}

function markdownImportMessage(error) {
  if (!(error instanceof MarkdownFileImportError)) {
    return "Markdown 导入失败，请重试。";
  }
  return {
    invalid_extension: "请选择 .md 格式的 Markdown 文档。",
    invalid_limit: "当前正文上限无效，请刷新页面。",
    too_large: "文档超过当前正文长度上限。",
    invalid_encoding: "Markdown 文档不是有效的 UTF-8 文本。",
    binary_content: "无法导入包含二进制内容的文件。",
  }[error.code] || "Markdown 导入失败，请重试。";
}

function announceMarkdownImport(message, level = "error") {
  document.dispatchEvent(
    new CustomEvent("kaj:feedback", {
      detail: {
        key: "author-markdown-import",
        level,
        message,
        timeout: level === "error" ? 6500 : 4500,
      },
    }),
  );
}

function initializeTiptap(root, source, changed) {
  const mount = root.querySelector("[data-tiptap-editor]");
  if (!(mount instanceof HTMLElement)) return null;
  let initial;
  try {
    initial = JSON.parse(source.value || "");
  } catch {
    initial = { type: "doc", content: [] };
  }
  const updateToolbar = (editor) => {
    root.querySelectorAll("[data-editor-command]").forEach((button) => {
      const command = button.dataset.editorCommand;
      const active =
        command === "heading"
          ? editor.isActive("heading", { level: 2 })
          : ["bold", "italic", "strike", "bulletList", "orderedList", "blockquote", "codeBlock"].includes(command)
            ? editor.isActive(command)
            : false;
      button.setAttribute("aria-pressed", String(active));
    });
  };
  const editor = new Editor({
    element: mount,
    extensions: [StarterKit.configure({ link: { openOnClick: false } }), AuthorImage],
    content: initial,
    editorProps: { attributes: { class: "author-tiptap__content" } },
    onUpdate: ({ editor: current }) => {
      source.value = JSON.stringify(normalizeTiptap(current.getJSON()));
      changed();
      updateToolbar(current);
    },
    onSelectionUpdate: ({ editor: current }) => updateToolbar(current),
    onCreate: ({ editor: current }) => updateToolbar(current),
  });
  root.querySelectorAll("[data-editor-command]").forEach((button) => {
    button.addEventListener("click", () => commandFor(editor, button.dataset.editorCommand)?.());
  });
  return editor;
}

function initializeAuthorEditor(root) {
  if (!(root instanceof HTMLFormElement) || root.dataset.editorBound === "true") return;
  const format = root.dataset.authorEditor;
  const localDraft = initializeLocalDraft(root);
  const source = root.querySelector("[data-editor-source]");
  const cloudState = root
    .closest("#author-editor-workspace")
    ?.querySelector("[data-editor-cloud-label]");
  const summaryMode = root.querySelector("[data-summary-mode]");
  const customSummary = root.querySelector("[data-custom-summary-field]");
  const commentsEnabled = root.querySelector("input[name='comments_enabled']");
  const commentRequirements = root.querySelectorAll(
    "input[name='comments_view_login'], input[name='comments_post_login']",
  );
  const tagInputs = root.querySelectorAll("input[name='tag_ids']");
  const tagCount = root.querySelector("[data-editor-tag-count]");
  const markdownImport = root.querySelector("[data-markdown-import]");
  const workspace = root.closest("#author-editor-workspace");
  const mediaDeleteDialog = workspace?.querySelector(
    "[data-body-media-delete-dialog]",
  );
  const localMedia = new Map();
  let previewTimer = null;
  let previewRequest = null;

  if (!(source instanceof HTMLTextAreaElement)) {
    localDraft?.dispose();
    return;
  }
  root.dataset.editorBound = "true";

  const setCloudState = (state, text) => {
    if (!(cloudState instanceof HTMLElement)) return;
    cloudState.dataset.cloudState = state;
    const icon = cloudState.querySelector(".lucide");
    cloudState.replaceChildren();
    if (icon) cloudState.append(icon);
    cloudState.append(document.createTextNode(text));
  };

  const patchLocalImages = () => {
    root.querySelectorAll("img").forEach((image) => {
      const id = image.dataset.authorMediaId || image.src.match(/\/_kaj\/media\/([0-9A-HJKMNP-TV-Z]{26})/)?.[1];
      if (id && localMedia.has(id)) image.src = localMedia.get(id);
    });
  };

  const updateMetric = () => {
    const metric = root.querySelector("[data-editor-body-metric]");
    if (!(metric instanceof HTMLElement)) return;
    const value = sourceMetrics(format, source.value);
    metric.textContent = `${value.characters} 字 · ${value.bytes} 字节 · ${value.media} 张图片`;
  };

  const requestPreview = async () => {
    const preview = root.querySelector("[data-editor-preview]");
    if (!(preview instanceof HTMLElement)) return;
    previewRequest?.abort();
    previewRequest = new AbortController();
    preview.setAttribute("aria-busy", "true");
    try {
      const response = await fetch(root.dataset.editorPreviewUrl, {
        method: "POST",
        body: new FormData(root),
        credentials: "same-origin",
        headers: { "X-Requested-With": "XMLHttpRequest" },
        signal: previewRequest.signal,
      });
      if (response.status !== 200 && response.status !== 422) {
        throw new Error("preview request failed");
      }
      const template = document.createElement("template");
      template.innerHTML = (await response.text()).trim();
      const replacement = template.content.firstElementChild;
      if (replacement) preview.replaceWith(replacement);
      patchLocalImages();
      document.dispatchEvent(new CustomEvent("kaj:editor-preview", { detail: { root } }));
    } catch (error) {
      if (error.name !== "AbortError") {
        preview.removeAttribute("aria-busy");
        const body = preview.querySelector("[data-preview-body], [data-preview-error]");
        if (body instanceof HTMLElement) {
          body.className = "author-editor-preview__error";
          body.dataset.previewError = "";
          body.setAttribute("role", "alert");
          body.replaceChildren(Object.assign(document.createElement("p"), {
            textContent: "预览暂时不可用，请稍后重试。",
          }));
        }
      }
    }
  };

  const schedulePreview = () => {
    updateMetric();
    localDraft?.schedule();
    setCloudState("dirty", "云端尚未包含这些修改");
    window.clearTimeout(previewTimer);
    previewTimer = window.setTimeout(requestPreview, 250);
  };

  const tiptap = format === "TIPTAP_JSON" ? initializeTiptap(root, source, schedulePreview) : null;

  const announce = (message, level = "success") => {
    document.dispatchEvent(
      new CustomEvent("kaj:feedback", {
        detail: {
          key: `author-body-media-${level}`,
          level,
          message,
          timeout: level === "error" ? 6500 : 4500,
        },
      }),
    );
  };

  const insertBodyImage = (assetId) => {
    if (!MEDIA_SOURCE.test(`media:${assetId}`)) return;
    if (tiptap) {
      tiptap
        .chain()
        .focus()
        .insertContent({
          type: "image",
          attrs: { src: `media:${assetId}`, alt: "" },
        })
        .run();
    } else {
      const insert = `\n![正文图片](media:${assetId})\n`;
      source.setRangeText(insert, source.selectionStart, source.selectionEnd, "end");
      source.dispatchEvent(new Event("input", { bubbles: true }));
      source.focus();
    }
    patchLocalImages();
  };

  const removeBodyImage = (assetId) => {
    if (tiptap) {
      const positions = [];
      tiptap.state.doc.descendants((node, position) => {
        if (node.type.name === "image" && node.attrs.src === `media:${assetId}`) {
          positions.push({ from: position, to: position + node.nodeSize });
        }
      });
      if (positions.length) {
        const transaction = tiptap.state.tr;
        positions
          .reverse()
          .forEach(({ from, to }) => transaction.delete(from, to));
        tiptap.view.dispatch(transaction);
      }
      return;
    }
    const reference = new RegExp(
      `!\\[[^\\]\\r\\n]*\\]\\(media:${assetId}(?:\\s+(?:"[^"\\r\\n]*"|'[^'\\r\\n]*'))?\\)`,
      "g",
    );
    const nextValue = source.value.replace(reference, "");
    if (nextValue !== source.value) {
      source.value = nextValue;
      source.dispatchEvent(new Event("input", { bubbles: true }));
    }
  };

  const refreshBodyMediaLibrary = async () => {
    const library = root.querySelector("[data-body-media-library]");
    const url = library?.dataset.bodyMediaLibraryUrl;
    if (!(library instanceof HTMLElement) || !url) return false;
    const wasOpen = library instanceof HTMLDetailsElement && library.open;
    try {
      const response = await fetch(url, {
        credentials: "same-origin",
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      if (!response.ok) throw new Error("media library request failed");
      const template = document.createElement("template");
      template.innerHTML = (await response.text()).trim();
      const replacement = template.content.firstElementChild;
      if (!(replacement instanceof HTMLElement)) {
        throw new Error("media library response invalid");
      }
      if (replacement instanceof HTMLDetailsElement) {
        replacement.open = wasOpen;
      }
      library.replaceWith(replacement);
      document.dispatchEvent(
        new CustomEvent("kaj:media-library", { detail: { root: replacement } }),
      );
      return true;
    } catch {
      announce("图片已处理，但列表刷新失败，重新打开编辑页即可找回。", "warning");
      return false;
    }
  };

  root.addEventListener("click", async (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const button = target.closest("[data-body-media-action]");
    if (!(button instanceof HTMLButtonElement) || !root.contains(button)) return;
    const action = button.dataset.bodyMediaAction;
    if (action === "insert") {
      insertBodyImage(button.dataset.bodyMediaId || "");
      announce("图片已插入正文。", "success");
      return;
    }
    if (action === "copy") {
      const reference = button.dataset.bodyMediaReference || "";
      const copyValue =
        format === "MARKDOWN" ? `![正文图片](${reference})` : reference;
      try {
        if (!navigator.clipboard || !copyValue) throw new Error("copy unavailable");
        await navigator.clipboard.writeText(copyValue);
        announce("图片引用已复制。", "success");
      } catch {
        announce("未能复制图片引用，请稍后重试。", "error");
      }
      return;
    }
    if (
      action === "delete" &&
      mediaDeleteDialog instanceof HTMLDialogElement
    ) {
      mediaDeleteDialog.dataset.bodyMediaId = button.dataset.bodyMediaId || "";
      mediaDeleteDialog.dataset.bodyMediaDeleteUrl =
        button.dataset.bodyMediaDeleteUrl || "";
      mediaDeleteDialog.dataset.dialogReturnFocus = button.id;
      const name = mediaDeleteDialog.querySelector("[data-body-media-delete-name]");
      const feedback = mediaDeleteDialog.querySelector(
        "[data-body-media-delete-feedback]",
      );
      if (name instanceof HTMLElement) {
        name.textContent = button.dataset.bodyMediaName || "";
      }
      if (feedback instanceof HTMLElement) feedback.replaceChildren();
      mediaDeleteDialog.showModal();
      requestAnimationFrame(() =>
        mediaDeleteDialog.querySelector("[data-dialog-cancel]")?.focus(),
      );
    }
  });

  const deleteConfirm = mediaDeleteDialog?.querySelector(
    "[data-body-media-delete-confirm]",
  );
  if (
    mediaDeleteDialog instanceof HTMLDialogElement &&
    deleteConfirm instanceof HTMLButtonElement
  ) {
    deleteConfirm.addEventListener("click", async () => {
      const assetId = mediaDeleteDialog.dataset.bodyMediaId || "";
      const deleteUrl = mediaDeleteDialog.dataset.bodyMediaDeleteUrl || "";
      const csrf = root.querySelector("input[name='csrfmiddlewaretoken']")?.value;
      const feedback = mediaDeleteDialog.querySelector(
        "[data-body-media-delete-feedback]",
      );
      if (!assetId || !deleteUrl || !csrf) return;
      deleteConfirm.disabled = true;
      mediaDeleteDialog.setAttribute("aria-busy", "true");
      if (feedback instanceof HTMLElement) feedback.textContent = "正在删除图片";
      try {
        const response = await fetch(deleteUrl, {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "X-CSRFToken": csrf,
            "X-Requested-With": "XMLHttpRequest",
          },
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || payload.ok !== true) {
          throw new Error(payload.message || "图片删除失败，请稍后重试。");
        }
        removeBodyImage(assetId);
        root.querySelector(`[data-body-media-item="${assetId}"]`)?.remove();
        await refreshBodyMediaLibrary();
        mediaDeleteDialog.close("deleted");
        announce(
          payload.message || "图片及服务器文件已删除。",
          payload.pending ? "warning" : "success",
        );
      } catch (error) {
        if (feedback instanceof HTMLElement) {
          feedback.textContent =
            error instanceof Error ? error.message : "图片删除失败，请稍后重试。";
        }
      } finally {
        deleteConfirm.disabled = false;
        mediaDeleteDialog.removeAttribute("aria-busy");
      }
    });
  }

  let markdownFile = null;
  let markdownImportOpen = false;
  const markdownImportTrigger = markdownImport?.querySelector("[data-markdown-import-trigger]");
  const markdownImportCard = markdownImport?.querySelector("[data-markdown-import-card]");
  const markdownImportFile = markdownImport?.querySelector("[data-markdown-import-file]");
  const markdownImportChoose = markdownImport?.querySelector("[data-markdown-import-choose]");
  const markdownImportName = markdownImport?.querySelector("[data-markdown-import-name]");
  const markdownImportApply = markdownImport?.querySelector("[data-markdown-import-apply]");
  const markdownImportClose = markdownImport?.querySelector("[data-markdown-import-close]");
  const markdownImportCancel = markdownImport?.querySelector("[data-markdown-import-cancel]");
  const resetMarkdownImport = () => {
    markdownFile = null;
    if (markdownImportFile instanceof HTMLInputElement) markdownImportFile.value = "";
    if (markdownImportName instanceof HTMLElement) markdownImportName.textContent = "尚未选择文档";
    if (markdownImportApply instanceof HTMLButtonElement) markdownImportApply.disabled = true;
  };
  const closeMarkdownImport = ({ focus = false, reset = false } = {}) => {
    markdownImportOpen = false;
    markdownImportCard?.setAttribute("hidden", "");
    markdownImportTrigger?.setAttribute("aria-expanded", "false");
    if (reset) resetMarkdownImport();
    if (focus) markdownImportTrigger?.focus({ preventScroll: true });
  };
  const openMarkdownImport = () => {
    if (!(markdownImportCard instanceof HTMLElement)) return;
    markdownImportOpen = true;
    markdownImportCard.removeAttribute("hidden");
    markdownImportTrigger?.setAttribute("aria-expanded", "true");
    window.requestAnimationFrame(() => markdownImportChoose?.focus({ preventScroll: true }));
  };
  const chooseMarkdownFile = () => {
    if (markdownImportFile instanceof HTMLInputElement && !markdownImportFile.disabled) {
      markdownImportFile.click();
    }
  };
  const selectMarkdownFile = () => {
    const selected = markdownImportFile?.files?.[0];
    markdownFile = selected instanceof File ? selected : null;
    if (markdownImportName instanceof HTMLElement) {
      markdownImportName.textContent = markdownFile?.name || "尚未选择文档";
    }
    if (markdownImportApply instanceof HTMLButtonElement) {
      markdownImportApply.disabled = !(markdownFile instanceof File);
    }
  };
  const applyMarkdownFile = async () => {
    if (!(markdownFile instanceof File) || markdownImportApply?.disabled) return;
    const limit = Number.parseInt(root.dataset.editorBodyLimit || "", 10);
    if (markdownImportApply instanceof HTMLButtonElement) markdownImportApply.disabled = true;
    markdownImportCard?.setAttribute("aria-busy", "true");
    try {
      const imported = await readMarkdownFile(markdownFile, limit);
      source.value = imported;
      source.dispatchEvent(new Event("input", { bubbles: true }));
      source.focus();
      source.setSelectionRange(imported.length, imported.length);
      announceMarkdownImport("Markdown 已导入，正文已覆盖。", "success");
      closeMarkdownImport({ reset: true });
    } catch (error) {
      announceMarkdownImport(markdownImportMessage(error));
      if (markdownImportApply instanceof HTMLButtonElement) {
        markdownImportApply.disabled = !(markdownFile instanceof File);
      }
    } finally {
      markdownImportCard?.removeAttribute("aria-busy");
    }
  };
  if (
    markdownImportTrigger instanceof HTMLButtonElement &&
    markdownImportCard instanceof HTMLElement &&
    markdownImportFile instanceof HTMLInputElement
  ) {
    markdownImportTrigger.addEventListener("click", () => {
      if (markdownImportOpen) closeMarkdownImport({ focus: true });
      else openMarkdownImport();
    });
    markdownImportChoose?.addEventListener("click", chooseMarkdownFile);
    markdownImportFile.addEventListener("change", selectMarkdownFile);
    markdownImportApply?.addEventListener("click", applyMarkdownFile);
    markdownImportClose?.addEventListener("click", () => closeMarkdownImport({ focus: true, reset: true }));
    markdownImportCancel?.addEventListener("click", () => closeMarkdownImport({ focus: true, reset: true }));
  }
  const closeMarkdownImportOnOutsideClick = (event) => {
    if (
      markdownImportOpen &&
      markdownImport instanceof HTMLElement &&
      !markdownImport.contains(event.target)
    ) {
      closeMarkdownImport();
    }
  };
  const closeMarkdownImportOnEscape = (event) => {
    if (markdownImportOpen && event.key === "Escape") {
      event.preventDefault();
      closeMarkdownImport({ focus: true });
    }
  };
  document.addEventListener("click", closeMarkdownImportOnOutsideClick);
  document.addEventListener("keydown", closeMarkdownImportOnEscape);

  if (!tiptap) source.addEventListener("input", schedulePreview);
  root.querySelectorAll("input, select, textarea").forEach((field) => {
    if (field === source || field.matches("[data-editor-transient]")) return;
    field.addEventListener("input", schedulePreview);
    field.addEventListener("change", schedulePreview);
  });

  const updateSummary = () => {
    if (customSummary instanceof HTMLElement && summaryMode instanceof HTMLSelectElement) {
      customSummary.hidden = summaryMode.value !== "CUSTOM";
    }
  };
  summaryMode?.addEventListener("change", updateSummary);
  updateSummary();

  const updateComments = () => {
    const enabled = commentsEnabled instanceof HTMLInputElement && commentsEnabled.checked;
    commentRequirements.forEach((field) => {
      field.disabled = !enabled;
      if (!enabled) field.checked = false;
    });
  };
  commentsEnabled?.addEventListener("change", updateComments);
  updateComments();

  const updateTags = () => {
    const selected = Array.from(tagInputs).filter((field) => field.checked).length;
    if (tagCount instanceof HTMLElement) tagCount.textContent = `已选择 ${selected} / 10`;
    tagInputs.forEach((field) => {
      field.disabled = selected >= 10 && !field.checked;
    });
  };
  tagInputs.forEach((field) => field.addEventListener("change", updateTags));
  updateTags();

  root.querySelectorAll("[data-editor-mode]").forEach((button) => {
    button.addEventListener("click", () => {
      root.dataset.mobileMode = button.dataset.editorMode;
      root.querySelectorAll("[data-editor-mode]").forEach((item) => {
        item.setAttribute("aria-pressed", String(item === button));
      });
    });
  });

  root.addEventListener("kaj:media-ready", (event) => {
    if (event.detail?.adapter === "article-cover") {
      schedulePreview();
      return;
    }
    if (event.detail?.adapter !== "article-body") return;
    const id = event.detail.assetId;
    if (event.detail.file instanceof File) localMedia.set(id, URL.createObjectURL(event.detail.file));
    insertBodyImage(id);
    refreshBodyMediaLibrary();
  });

  root.addEventListener("kaj:cloud-save-failed", () => {
    setCloudState("error", "云端保存失败，本地稿已保留");
  });

  root.addEventListener("submit", () => {
    if (tiptap) source.value = JSON.stringify(normalizeTiptap(tiptap.getJSON()));
    localDraft?.flushForCloudSave();
    setCloudState("saving", "正在保存云端草稿");
  });

  const clearLocalMedia = () => {
    localMedia.forEach((url) => URL.revokeObjectURL(url));
    localMedia.clear();
  };
  window.addEventListener("pagehide", clearLocalMedia, { once: true });
  activeEditors.set(root, () => {
    window.clearTimeout(previewTimer);
    previewRequest?.abort();
    localDraft?.dispose();
    tiptap?.destroy();
    document.removeEventListener("click", closeMarkdownImportOnOutsideClick);
    document.removeEventListener("keydown", closeMarkdownImportOnEscape);
    window.removeEventListener("pagehide", clearLocalMedia);
    clearLocalMedia();
    activeEditors.delete(root);
  });
  updateMetric();
  if (localDraft?.restored) {
    if (cloudState?.dataset.cloudState !== "conflict") {
      if (root.dataset.cloudError === "true") {
        setCloudState("error", "云端保存失败，本地稿已保留");
      } else {
        setCloudState("dirty", "云端尚未包含已恢复的本地稿");
      }
    }
    requestPreview();
  }
}

export function initializeAuthorEditors(scope = document) {
  if (scope instanceof HTMLFormElement && scope.matches("form[data-author-editor]")) {
    initializeAuthorEditor(scope);
  }
  scope.querySelectorAll?.("form[data-author-editor]").forEach(initializeAuthorEditor);
}

export function destroyAuthorEditors(scope) {
  const forms = [];
  if (scope instanceof HTMLFormElement && scope.matches("form[data-author-editor]")) {
    forms.push(scope);
  }
  scope?.querySelectorAll?.("form[data-author-editor]").forEach((form) => forms.push(form));
  forms.forEach((form) => activeEditors.get(form)?.());
}
