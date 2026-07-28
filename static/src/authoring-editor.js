import { Editor, Node, mergeAttributes } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";

import { initializeLocalDraft } from "./authoring-local-draft.js";

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
  const editPane = root.querySelector('[data-editor-pane="edit"]');
  const commentsEnabled = root.querySelector("input[name='comments_enabled']");
  const commentRequirements = root.querySelectorAll(
    "input[name='comments_view_login'], input[name='comments_post_login']",
  );
  const tagInputs = root.querySelectorAll("input[name='tag_ids']");
  const tagCount = root.querySelector("[data-editor-tag-count]");
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
  if (!tiptap) source.addEventListener("input", schedulePreview);
  root.querySelectorAll("input, select, textarea").forEach((field) => {
    if (field === source) return;
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

  editPane?.addEventListener("focusin", () => {
    root.dataset.editorInputActive = "true";
  });
  editPane?.addEventListener("focusout", () => {
    requestAnimationFrame(() => {
      if (!editPane.contains(document.activeElement)) {
        delete root.dataset.editorInputActive;
      }
    });
  });

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
    if (tiptap) {
      tiptap.chain().focus().insertContent({ type: "image", attrs: { src: `media:${id}`, alt: "" } }).run();
    } else {
      const insert = `\n![正文图片](media:${id})\n`;
      source.setRangeText(insert, source.selectionStart, source.selectionEnd, "end");
      source.dispatchEvent(new Event("input", { bubbles: true }));
      source.focus();
    }
    patchLocalImages();
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
