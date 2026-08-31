import { Editor } from "@tiptap/core";
import Link from "@tiptap/extension-link";

import { initializeLocalDraft } from "./authoring-local-draft.js";
import {
  MarkdownFileImportError,
  readMarkdownFile,
} from "./markdown-file-import.js";
import { initializeEditorPreviewScroll } from "./editor-preview-scroll.js";
import { recordAuthorEditorPerformance } from "./editor-performance.js";
import {
  createAuthorHeadingExtension,
  initializeEditorOutline,
  normalizeHeadingDocument,
} from "./editor-outline.js";
import {
  EDITOR_LINK_OPTIONS,
  initializeEditorLinkDialog,
} from "./editor-link-dialog.js";
import {
  initializeEditorImagePaste,
  isPendingImageSource,
} from "./editor-image-paste.js";
import {
  AUTHOR_MEDIA_SOURCE,
  createAuthorImageExtension,
  initializeEditorImageWorkflow,
  normalizeAuthorImageAttributes,
} from "./editor-image.js";
import {
  createAuthorInputExtensions,
  createAuthorStarterKit,
} from "./editor-input-behaviors.js";
import {
  createAuthorPasteExtensions,
  initializeEditorPasteContract,
} from "./editor-paste-contract.js";
import { initializeEditorBlockMenu } from "./editor-block-menu.js";
import {
  createAuthorAttachmentExtension,
  normalizeAuthorAttachmentAttributes,
  removeAuthorAttachment,
  upsertAuthorAttachment,
} from "./editor-attachment.js";
import {
  createAuthorCodeBlockExtension,
  normalizeCodeLanguage,
} from "./editor-code-block.js";
import { initializeEditorSelectionToolbar } from "./editor-selection-toolbar.js";
import { initializeEditorSlashMenu } from "./editor-slash-menu.js";
import { createAuthorStructureExtensions } from "./editor-structure-blocks.js";
import {
  createAuthorTableExtensions,
  initializeEditorTableToolbar,
  normalizeAuthorTableAttributes,
} from "./editor-table.js";
import { initializeEditorToolbar } from "./editor-toolbar.js";
import {
  disposeEditorUploadTracker,
  editorUploadTrackerFor,
} from "./editor-upload-state.js";
import {
  createAuthorEmbedExtension,
  initializeEditorEmbedDialog,
  normalizeAuthorEmbedAttributes,
} from "./editor-embed.js";
import {
  createAuthorLatexExtension,
  initializeEditorLatexDialog,
  normalizeAuthorLatexAttributes,
} from "./editor-latex.js";

const activeEditors = new WeakMap();

const AuthorLink = Link.extend({
  addAttributes() {
    return {
      href: { default: null },
      title: { default: null },
    };
  },
}).configure({
  ...EDITOR_LINK_OPTIONS,
  openOnClick: false,
  HTMLAttributes: {},
});

function normalizeTiptap(value) {
  if (Array.isArray(value)) {
    return value.map(normalizeTiptap).filter((item) => item !== null);
  }
  if (!value || typeof value !== "object") {
    return value;
  }
  if (value.type === "image" && isPendingImageSource(value.attrs?.src)) {
    return null;
  }
  const normalized = {};
  Object.entries(value).forEach(([key, item]) => {
    if (item === null || item === undefined) {
      return;
    }
    if (key === "attrs" && value.type === "image") {
      normalized.attrs = normalizeAuthorImageAttributes(item);
      return;
    }
    if (key === "attrs" && value.type === "attachment") {
      normalized.attrs = normalizeAuthorAttachmentAttributes(item);
      return;
    }
    if (key === "attrs" && value.type === "embed") {
      normalized.attrs = normalizeAuthorEmbedAttributes(item);
      return;
    }
    if (key === "attrs" && value.type === "latexBlock") {
      normalized.attrs = normalizeAuthorLatexAttributes(item);
      return;
    }
    if (key === "attrs" && value.type === "codeBlock") {
      normalized.attrs = { language: normalizeCodeLanguage(item.language) };
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
    if (key === "attrs") {
      const tableAttributes = normalizeAuthorTableAttributes(value.type, item);
      if (tableAttributes === null) return;
      normalized.attrs = normalizeTiptap(tableAttributes);
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

function initializeTiptap(root, source, changed, selectionChanged, announce) {
  const mount = root.querySelector("[data-tiptap-editor]");
  if (!(mount instanceof HTMLElement)) return null;
  let initial;
  try {
    initial = normalizeHeadingDocument(normalizeTiptap(JSON.parse(source.value || "")));
    source.value = JSON.stringify(initial);
  } catch {
    initial = { type: "doc", content: [] };
  }
  let toolbarController = null;
  let blockMenuController = null;
  let linkController = null;
  let selectionToolbarController = null;
  let slashMenuController = null;
  let tableToolbarController = null;
  let outlineController = null;
  let embedController = null;
  let latexController = null;
  let pasteController = null;
  const enabledEmbedSources = (() => {
    try {
      const value = JSON.parse(
        root.querySelector("#editor-embed-sources")?.textContent || "[]",
      );
      return Array.isArray(value) ? value : [];
    } catch {
      return [];
    }
  })();
  const updateToolbar = () => toolbarController?.update();
  const editor = new Editor({
    element: mount,
    extensions: [
      createAuthorStarterKit(),
      createAuthorHeadingExtension(),
      AuthorLink,
      createAuthorImageExtension(),
      createAuthorAttachmentExtension({
        getMetadata: (assetId) => {
          const picker = root.querySelector(
            '[data-media-picker="article-attachment"]',
          );
          const selected = picker?.querySelector("[data-media-value]")?.value;
          if (!picker || selected !== assetId) return null;
          return {
            name: picker.dataset.mediaCurrentName || "文章附件",
            mime: picker.dataset.mediaCurrentMime || "",
            size: Number(picker.dataset.mediaCurrentSize || 0),
          };
        },
      }),
      createAuthorEmbedExtension({
        enabledSources: enabledEmbedSources,
        openDialog: (options) => embedController?.open(options) || false,
      }),
      createAuthorLatexExtension({
        openDialog: (options) => latexController?.open(options) || false,
      }),
      createAuthorCodeBlockExtension(),
      ...createAuthorInputExtensions({
        openLink: () => linkController?.open() || false,
      }),
      ...createAuthorPasteExtensions({ announce, enabledEmbedSources }),
      ...createAuthorStructureExtensions(),
      ...createAuthorTableExtensions(),
    ],
    content: initial,
    editorProps: { attributes: { class: "author-tiptap__content" } },
    onUpdate: ({ editor: current }) => {
      const startedAt = performance.now();
      try {
        source.value = JSON.stringify(normalizeTiptap(current.getJSON()));
        changed();
        updateToolbar();
        selectionChanged();
      } finally {
        recordAuthorEditorPerformance("editor_update", performance.now() - startedAt, {
          units: current.state.doc.nodeSize,
        });
      }
    },
    onSelectionUpdate: () => {
      updateToolbar();
      selectionChanged();
    },
  });
  pasteController = initializeEditorPasteContract({
    editor,
    announce,
    enabledEmbedSources,
  });
  linkController = initializeEditorLinkDialog({ root, editor });
  embedController = initializeEditorEmbedDialog({
    root,
    editor,
    enabledSources: enabledEmbedSources,
  });
  latexController = initializeEditorLatexDialog({ root, editor });
  const actions = {
    "link-dialog": ({ trigger }) => linkController.open(trigger),
    "embed-dialog": ({ trigger }) => embedController.open({ trigger }),
    "latex-dialog": ({ trigger }) => latexController.open({ trigger }),
  };
  toolbarController = initializeEditorToolbar({
    root,
    editor,
    actions,
  });
  selectionToolbarController = initializeEditorSelectionToolbar({
    root,
    editor,
    actions,
  });
  blockMenuController = initializeEditorBlockMenu({ root, editor });
  slashMenuController = initializeEditorSlashMenu({ root, editor, actions });
  tableToolbarController = initializeEditorTableToolbar({ root, editor });
  outlineController = initializeEditorOutline({ root, editor });
  toolbarController.update();
  return {
    editor,
    dispose: () => {
      pasteController?.dispose();
      tableToolbarController?.dispose();
      outlineController?.dispose();
      slashMenuController?.dispose();
      blockMenuController?.dispose();
      selectionToolbarController?.dispose();
      toolbarController?.dispose();
      linkController?.dispose();
      embedController?.dispose();
      latexController?.dispose();
    },
  };
}

function initializeAuthorEditor(root) {
  if (!(root instanceof HTMLFormElement) || root.dataset.editorBound === "true") return;
  const format = root.dataset.authorEditor;
  const localDraft = initializeLocalDraft(root);
  const uploadTracker = editorUploadTrackerFor(root);
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
  const markdownImport = root.querySelector("[data-markdown-import]");
  const workspace = root.closest("#author-editor-workspace");
  const mediaDeleteDialog = workspace?.querySelector(
    "[data-body-media-delete-dialog]",
  );
  const localMedia = new Map();
  let previewTimer = null;
  let previewRequest = null;
  let previewScroll = null;
  let imagePaste = null;
  let imageWorkflow = null;
  let latexController = null;
  const previewToggle = root.querySelector("[data-editor-preview-toggle]");

  if (!(source instanceof HTMLTextAreaElement)) {
    localDraft?.dispose();
    disposeEditorUploadTracker(root);
    return;
  }
  root.dataset.editorBound = "true";

  const setPreviewCollapsed = (collapsed) => {
    root.dataset.previewCollapsed = String(collapsed);
    if (previewToggle instanceof HTMLButtonElement) {
      const label = collapsed ? "展开实时预览" : "收起实时预览";
      previewToggle.setAttribute("aria-expanded", String(!collapsed));
      previewToggle.setAttribute("aria-label", label);
      previewToggle.title = label;
    }
    if (!collapsed) {
      requestAnimationFrame(() => previewScroll?.refresh());
    }
  };
  const togglePreview = () => {
    setPreviewCollapsed(root.dataset.previewCollapsed !== "true");
  };
  previewToggle?.addEventListener("click", togglePreview);
  setPreviewCollapsed(root.dataset.previewCollapsed === "true");

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

  const registerLocalMedia = (assetId, file) => {
    if (!(file instanceof File)) return;
    const previous = localMedia.get(assetId);
    if (previous) URL.revokeObjectURL(previous);
    localMedia.set(assetId, URL.createObjectURL(file));
    patchLocalImages();
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
    const startedAt = performance.now();
    let metricOutcome = "error";
    let requestRecorded = false;
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
      metricOutcome = response.status === 422 ? "rejected" : "success";
      const responseHtml = await response.text();
      recordAuthorEditorPerformance(
        "preview_request",
        performance.now() - startedAt,
        { outcome: metricOutcome },
      );
      requestRecorded = true;
      const renderStartedAt = performance.now();
      const template = document.createElement("template");
      try {
        template.innerHTML = responseHtml.trim();
        const replacement = template.content.firstElementChild;
        if (replacement) preview.replaceWith(replacement);
        patchLocalImages();
        previewScroll?.refresh();
        document.dispatchEvent(
          new CustomEvent("kaj:editor-preview", { detail: { root } }),
        );
      } catch (error) {
        metricOutcome = "error";
        throw error;
      } finally {
        recordAuthorEditorPerformance(
          "preview_render",
          performance.now() - renderStartedAt,
          { outcome: metricOutcome },
        );
      }
    } catch (error) {
      if (error.name === "AbortError") metricOutcome = "cancelled";
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
    } finally {
      if (!requestRecorded) {
        recordAuthorEditorPerformance(
          "preview_request",
          performance.now() - startedAt,
          { outcome: metricOutcome },
        );
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

  const announce = (
    message,
    level = "success",
    key = `author-body-media-${level}`,
  ) => {
    document.dispatchEvent(
      new CustomEvent("kaj:feedback", {
        detail: {
          key,
          level,
          message,
          timeout: level === "error" ? 6500 : 4500,
        },
      }),
    );
  };

  const tiptapController =
    format === "TIPTAP_JSON"
      ? initializeTiptap(
          root,
          source,
          schedulePreview,
          () => previewScroll?.syncSelection(),
          announce,
        )
      : null;
  const tiptap = tiptapController?.editor || null;
  if (!tiptap) {
    latexController = initializeEditorLatexDialog({ root, source });
  }
  previewScroll = initializeEditorPreviewScroll({ root, source, format, tiptap });

  const insertBodyImage = (assetId) => {
    if (!AUTHOR_MEDIA_SOURCE.test(`media:${assetId}`)) return;
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

  imagePaste = initializeEditorImagePaste({
    root,
    source,
    format,
    tiptap,
    announce: (message, level) =>
      announce(message, level, "author-body-media-paste"),
    registerLocalMedia,
    refreshLibrary: refreshBodyMediaLibrary,
  });
  if (tiptap) {
    imageWorkflow = initializeEditorImageWorkflow({
      root,
      editor: tiptap,
      announce: (message, level) =>
        announce(message, level, "author-body-image-workflow"),
      registerLocalMedia,
      refreshLibrary: refreshBodyMediaLibrary,
    });
  }

  root.addEventListener("click", async (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const attachmentInsert = target.closest("[data-attachment-card-insert]");
    if (
      attachmentInsert instanceof HTMLButtonElement &&
      root.contains(attachmentInsert)
    ) {
      const assetId = root.querySelector(
        '[data-media-picker="article-attachment"] [data-media-value]',
      )?.value;
      if (tiptap && upsertAuthorAttachment(tiptap, assetId || "")) {
        announce("附件卡片已插入正文。", "success", "author-attachment-card");
      }
      return;
    }
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
  const markdownLatexTrigger = root.querySelector("[data-latex-trigger]");
  const openMarkdownLatex = () => latexController?.openMarkdown(markdownLatexTrigger);
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
    if (
      uploadTracker?.pendingCount ||
      imagePaste?.pendingCount ||
      imageWorkflow?.pendingCount
    ) {
      if (uploadTracker?.pendingCount) uploadTracker.announcePending();
      else if (imageWorkflow?.pendingCount) imageWorkflow.announcePending();
      else imagePaste.announcePending();
      return;
    }
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
  markdownLatexTrigger?.addEventListener("click", openMarkdownLatex);

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

  root.querySelectorAll("[data-editor-mode]").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.dataset.editorMode === "preview") {
        setPreviewCollapsed(false);
      }
      root.dataset.mobileMode = button.dataset.editorMode;
      root.querySelectorAll("[data-editor-mode]").forEach((item) => {
        item.setAttribute("aria-pressed", String(item === button));
      });
      previewScroll?.refresh();
    });
  });

  root.addEventListener("kaj:media-ready", (event) => {
    if (event.detail?.adapter === "article-attachment") {
      schedulePreview();
      if (tiptap && upsertAuthorAttachment(tiptap, event.detail.assetId || "")) {
        announce(
          "附件已上传并插入正文。",
          "success",
          "author-attachment-card",
        );
      }
      return;
    }
    if (event.detail?.adapter === "article-cover") {
      schedulePreview();
      return;
    }
    if (event.detail?.adapter !== "article-body") return;
    const id = event.detail.assetId;
    registerLocalMedia(id, event.detail.file);
    insertBodyImage(id);
    refreshBodyMediaLibrary();
  });

  const attachmentValue = root.querySelector(
    '[data-media-picker="article-attachment"] [data-media-value]',
  );
  attachmentValue?.addEventListener("input", () => {
    if (tiptap && !attachmentValue.value) removeAuthorAttachment(tiptap);
  });

  root.addEventListener("kaj:cloud-save-failed", () => {
    setCloudState("error", "云端保存失败，本地稿已保留");
  });

  root.addEventListener("submit", (event) => {
    if (
      uploadTracker?.pendingCount ||
      imagePaste?.pendingCount ||
      imageWorkflow?.pendingCount
    ) {
      event.preventDefault();
      event.stopImmediatePropagation();
      if (uploadTracker?.pendingCount) uploadTracker.announcePending();
      else if (imageWorkflow?.pendingCount) imageWorkflow.announcePending();
      else imagePaste.announcePending();
      return;
    }
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
    previewScroll?.dispose();
    imagePaste?.dispose();
    imageWorkflow?.dispose();
    disposeEditorUploadTracker(root);
    tiptapController?.dispose();
    latexController?.dispose();
    tiptap?.destroy();
    previewToggle?.removeEventListener("click", togglePreview);
    document.removeEventListener("click", closeMarkdownImportOnOutsideClick);
    document.removeEventListener("keydown", closeMarkdownImportOnEscape);
    markdownLatexTrigger?.removeEventListener("click", openMarkdownLatex);
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
