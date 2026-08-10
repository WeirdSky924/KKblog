import { Node, mergeAttributes } from "@tiptap/core";
import { NodeSelection } from "@tiptap/pm/state";
import {
  ImageUp,
  PencilLine,
  Save,
  Trash2,
  X,
  createIcons,
} from "lucide";

import { dispatchIsolatedEditorTransaction } from "./editor-history.js";
import { isPendingImageSource } from "./editor-image-paste.js";
import {
  MediaUploadRequestError,
  uploadMediaFile,
} from "./media-upload.js";
import { editorUploadTrackerFor } from "./editor-upload-state.js";

export const AUTHOR_MEDIA_SOURCE = /^media:([0-9A-HJKMNP-TV-Z]{26})$/;
export const AUTHOR_IMAGE_WIDTHS = Object.freeze([25, 50, 75, 100]);

const VIEWPORT_GUTTER = 8;
const TOOLBAR_GAP = 8;

export function normalizeAuthorImageAttributes(attributes) {
  const source = typeof attributes?.src === "string" ? attributes.src : "";
  const normalized = source ? { src: source } : {};
  for (const name of ["alt", "title"]) {
    const value = attributes?.[name];
    if (typeof value === "string" && value) normalized[name] = value;
  }
  const width = Number(attributes?.width ?? 100);
  if (AUTHOR_IMAGE_WIDTHS.includes(width) && width !== 100) {
    normalized.width = width;
  }
  return normalized;
}

function mediaAttributes(attributes) {
  const normalized = normalizeAuthorImageAttributes(attributes);
  const matched = String(normalized.src || "").match(AUTHOR_MEDIA_SOURCE);
  const mediaId = matched?.[1] || "";
  return {
    ...normalized,
    src: mediaId ? `/_kaj/media/${mediaId}` : "",
    "data-author-media-id": mediaId,
    "data-width": String(normalized.width || 100),
  };
}

const AuthorImage = Node.create({
  name: "image",
  group: "block",
  atom: true,
  draggable: true,
  selectable: true,
  addAttributes() {
    return {
      src: {
        default: null,
        parseHTML: (image) => {
          const mediaId = image.getAttribute("data-author-media-id") || "";
          return AUTHOR_MEDIA_SOURCE.test(`media:${mediaId}`)
            ? `media:${mediaId}`
            : null;
        },
      },
      alt: { default: null },
      title: { default: null },
      width: {
        default: 100,
        parseHTML: (image) => {
          const width = Number(image.getAttribute("data-width") || 100);
          return AUTHOR_IMAGE_WIDTHS.includes(width) ? width : 100;
        },
      },
    };
  },
  parseHTML() {
    return [{ tag: "img[data-author-media-id]" }];
  },
  renderHTML({ HTMLAttributes }) {
    const source = String(HTMLAttributes.src || "");
    if (isPendingImageSource(source)) {
      return [
        "span",
        {
          class: "author-tiptap-upload",
          "data-author-upload-source": source,
          contenteditable: "false",
          role: "status",
        },
        "正在上传图片",
      ];
    }
    const attributes = mediaAttributes(HTMLAttributes);
    delete attributes.width;
    return ["img", mergeAttributes(attributes)];
  },
});

export function createAuthorImageExtension() {
  return AuthorImage;
}

function clamp(value, minimum, maximum) {
  if (maximum < minimum) return minimum;
  return Math.min(Math.max(value, minimum), maximum);
}

export function imageToolbarPosition({
  imageLeft,
  imageRight,
  imageTop,
  imageBottom,
  toolbarWidth,
  toolbarHeight,
  viewportLeft,
  viewportTop,
  viewportWidth,
  viewportHeight,
  clippingTop,
  clippingBottom,
}) {
  const safeLeft = viewportLeft + VIEWPORT_GUTTER;
  const safeRight = viewportLeft + viewportWidth - VIEWPORT_GUTTER;
  const left = clamp(
    (clamp(imageLeft, safeLeft, safeRight) +
      clamp(imageRight, safeLeft, safeRight)) /
      2,
    safeLeft + toolbarWidth / 2,
    safeRight - toolbarWidth / 2,
  );
  const safeTop = Math.max(viewportTop, clippingTop) + VIEWPORT_GUTTER;
  const safeBottom =
    Math.min(viewportTop + viewportHeight, clippingBottom) - VIEWPORT_GUTTER;
  const above = imageTop - toolbarHeight - TOOLBAR_GAP;
  if (above >= safeTop) return { left, top: above, placement: "above" };
  return {
    left,
    top: clamp(
      imageTop + VIEWPORT_GUTTER,
      safeTop,
      Math.max(safeTop, Math.min(imageBottom, safeBottom) - toolbarHeight),
    ),
    placement: "inside",
  };
}

function element(tag, { className, text, attributes = {} } = {}) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  Object.entries(attributes).forEach(([name, value]) =>
    node.setAttribute(name, value),
  );
  return node;
}

function iconButton(action, label, icon, danger = false) {
  const button = element("button", {
    className: "author-image-toolbar__command",
    attributes: { type: "button", "aria-label": label, title: label },
  });
  button.dataset.imageAction = action;
  if (danger) button.dataset.danger = "";
  button.append(element("i", { attributes: { "data-lucide": icon } }));
  return button;
}

function renderToolbar() {
  const toolbar = element("div", {
    className: "author-image-toolbar",
    attributes: { role: "toolbar", "aria-label": "图片编辑" },
  });
  toolbar.dataset.editorImageToolbar = "";
  toolbar.hidden = true;
  toolbar.append(
    iconButton("replace", "替换图片", "image-up"),
    iconButton("edit", "编辑图片信息", "pencil-line"),
    iconButton("delete", "从正文移除图片", "trash-2", true),
  );
  const input = element("input", {
    className: "visually-hidden",
    attributes: {
      type: "file",
      accept: ".png,.jpg,.jpeg,.gif,.webp,image/png,image/jpeg,image/gif,image/webp",
      tabindex: "-1",
      "aria-hidden": "true",
    },
  });
  input.dataset.imageReplaceFile = "";
  toolbar.append(input);
  return toolbar;
}

function actionButton(label, icon, primary = false) {
  const button = element("button", {
    className: primary ? "button button--primary" : "button button--secondary",
    attributes: { type: "button" },
  });
  button.append(
    element("i", { attributes: { "data-lucide": icon } }),
    element("span", { text: label }),
  );
  return button;
}

function renderDialog() {
  const dialog = element("dialog", {
    className: "author-image-dialog",
    attributes: { "aria-labelledby": "author-image-dialog-title" },
  });
  dialog.dataset.editorImageDialog = "";
  const form = element("form", { attributes: { method: "dialog" } });
  const header = element("header");
  const heading = element("h3", {
    text: "图片信息",
    attributes: { id: "author-image-dialog-title" },
  });
  const close = iconButton("close", "关闭图片设置", "x");
  close.className = "author-image-dialog__close";
  header.append(heading, close);

  const altLabel = element("label", { text: "替代文字" });
  const altInput = element("input", {
    attributes: {
      type: "text",
      autocomplete: "off",
      placeholder: "说明图片传达的内容",
    },
  });
  altInput.dataset.imageAlt = "";
  altLabel.append(altInput);
  const titleLabel = element("label", { text: "图片标题（可选）" });
  const titleInput = element("input", {
    attributes: { type: "text", autocomplete: "off" },
  });
  titleInput.dataset.imageTitle = "";
  titleLabel.append(titleInput);

  const widths = element("fieldset", {
    className: "author-image-dialog__widths",
  });
  widths.append(element("legend", { text: "显示宽度" }));
  const widthOptions = element("div");
  AUTHOR_IMAGE_WIDTHS.forEach((width) => {
    const label = element("label");
    const input = element("input", {
      attributes: {
        type: "radio",
        name: "author-image-width",
        value: String(width),
      },
    });
    label.append(input, element("span", { text: `${width}%` }));
    widthOptions.append(label);
  });
  widths.append(widthOptions);

  const actions = element("div", { className: "author-image-dialog__actions" });
  const cancel = actionButton("取消", "x");
  cancel.dataset.imageDialogCancel = "";
  const apply = actionButton("应用", "save", true);
  apply.type = "submit";
  actions.append(cancel, apply);
  form.append(header, altLabel, titleLabel, widths, actions);
  dialog.append(form);
  return dialog;
}

function selectedImage(editor) {
  const selection = editor?.state?.selection;
  if (!(selection instanceof NodeSelection) || selection.node.type.name !== "image") {
    return null;
  }
  return { node: selection.node, position: selection.from };
}

function imageElement(editor, position) {
  const node = editor.view?.nodeDOM?.(position);
  if (!(node instanceof Element)) return null;
  if (node.matches("img, [data-author-upload-source]")) return node;
  return node.querySelector("img, [data-author-upload-source]");
}

function imageUploadError(error) {
  return error instanceof MediaUploadRequestError
    ? error.message
    : "图片替换失败，请重新选择后重试。";
}

export function initializeEditorImageWorkflow({
  root,
  editor,
  announce,
  registerLocalMedia,
  refreshLibrary,
}) {
  const mount = root.querySelector("[data-tiptap-editor]");
  const picker = root.querySelector('[data-media-picker="article-body"]');
  const uploadUrl = picker?.dataset.mediaUploadUrl || "";
  const csrfToken =
    picker?.querySelector("input[name='csrfmiddlewaretoken']")?.value || "";
  const uploadTracker = editorUploadTrackerFor(root);
  if (!(mount instanceof HTMLElement) || !uploadUrl || !csrfToken) return null;

  const toolbar = renderToolbar();
  const replaceInput = toolbar.querySelector("[data-image-replace-file]");
  const host = root.closest("#author-editor-workspace") || document.body;
  const dialog = renderDialog();
  const dialogForm = dialog.querySelector("form");
  const altInput = dialog.querySelector("[data-image-alt]");
  const titleInput = dialog.querySelector("[data-image-title]");
  mount.before(toolbar);
  host.append(dialog);
  for (const iconRoot of [toolbar, dialog]) {
    createIcons({
      root: iconRoot,
      icons: { ImageUp, PencilLine, Save, Trash2, X },
      attrs: { "aria-hidden": "true", focusable: "false" },
    });
  }

  const pending = new Set();
  let frame = null;
  let dismissed = false;
  let dialogPosition = null;

  const updatePendingState = () => {
    if (pending.size) root.dataset.imageReplaceCount = String(pending.size);
    else delete root.dataset.imageReplaceCount;
  };

  const positionToolbar = () => {
    frame = null;
    const selected = selectedImage(editor);
    const image = selected && imageElement(editor, selected.position);
    if (!selected || !image || dismissed || dialog.open) {
      toolbar.hidden = true;
      return;
    }
    const imageRect = image.getBoundingClientRect();
    const clippingRect = mount.getBoundingClientRect();
    const viewport = window.visualViewport;
    toolbar.hidden = false;
    toolbar.querySelector('[data-image-action="replace"]').disabled =
      pending.size > 0;
    const placement = imageToolbarPosition({
      imageLeft: imageRect.left,
      imageRight: imageRect.right,
      imageTop: imageRect.top,
      imageBottom: imageRect.bottom,
      toolbarWidth: toolbar.offsetWidth,
      toolbarHeight: toolbar.offsetHeight,
      viewportLeft: viewport?.offsetLeft || 0,
      viewportTop: viewport?.offsetTop || 0,
      viewportWidth: viewport?.width || window.innerWidth,
      viewportHeight: viewport?.height || window.innerHeight,
      clippingTop: clippingRect.top,
      clippingBottom: clippingRect.bottom,
    });
    toolbar.style.left = `${placement.left}px`;
    toolbar.style.top = `${placement.top}px`;
    toolbar.dataset.placement = placement.placement;
  };

  const schedule = () => {
    if (frame === null) frame = window.requestAnimationFrame(positionToolbar);
  };

  const restoreSelection = () => {
    if (!Number.isInteger(dialogPosition)) return;
    const node = editor.state.doc.nodeAt(dialogPosition);
    if (node?.type.name !== "image") return;
    editor.view.dispatch(
      editor.state.tr.setSelection(
        NodeSelection.create(editor.state.doc, dialogPosition),
      ),
    );
    editor.view.focus();
  };

  const openDialog = () => {
    const selected = selectedImage(editor);
    if (!selected) return;
    dialogPosition = selected.position;
    altInput.value = selected.node.attrs.alt || "";
    titleInput.value = selected.node.attrs.title || "";
    const width = AUTHOR_IMAGE_WIDTHS.includes(Number(selected.node.attrs.width))
      ? Number(selected.node.attrs.width)
      : 100;
    dialog.querySelector(
      `input[name="author-image-width"][value="${width}"]`,
    ).checked = true;
    toolbar.hidden = true;
    dialog.showModal();
    window.requestAnimationFrame(() => altInput.focus({ preventScroll: true }));
  };

  const applyDialog = (event) => {
    event.preventDefault();
    const node = Number.isInteger(dialogPosition)
      ? editor.state.doc.nodeAt(dialogPosition)
      : null;
    if (node?.type.name !== "image") {
      dialog.close("missing");
      announce("图片已不在正文中，设置没有应用。", "warning");
      return;
    }
    const checked = dialog.querySelector(
      'input[name="author-image-width"]:checked',
    );
    const attributes = normalizeAuthorImageAttributes({
      ...node.attrs,
      alt: altInput.value.trim(),
      title: titleInput.value.trim(),
      width: Number(checked?.value || 100),
    });
    dispatchIsolatedEditorTransaction(
      editor,
      editor.state.tr.setNodeMarkup(dialogPosition, undefined, attributes),
    );
    dialog.close("applied");
    announce("图片信息已更新。", "success");
  };

  const removeSelected = () => {
    const selected = selectedImage(editor);
    if (!selected) return;
    dispatchIsolatedEditorTransaction(
      editor,
      editor.state.tr.delete(
        selected.position,
        selected.position + selected.node.nodeSize,
      ),
      { focus: true },
    );
    announce("图片已从正文移除，图片库仍会保留。", "success");
  };

  const replacementTarget = (target = null) => {
    if (!target) return selectedImage(editor);
    const atPosition = editor.state.doc.nodeAt(target.position);
    if (atPosition?.type.name === "image" && atPosition.attrs.src === target.source) {
      return { node: atPosition, position: target.position };
    }
    let matched = null;
    editor.state.doc.descendants((node, position) => {
      if (!matched && node.type.name === "image" && node.attrs.src === target.source) {
        matched = { node, position };
      }
    });
    return matched;
  };

  const replaceSelected = async (file, retryTarget = null) => {
    const selected = replacementTarget(retryTarget);
    if (!selected || !(file instanceof File) || pending.size) return;
    const controller = new AbortController();
    const job = {
      controller,
      position: selected.position,
      source: selected.node.attrs.src,
      taskKey: retryTarget?.taskKey || `image-replace-${crypto.randomUUID()}`,
      completing: false,
      removed: false,
    };
    const uploadTask = uploadTracker?.begin({
      key: job.taskKey,
      label: `替换图片 · ${file.name || "图片"}`,
      onCancel: () => controller.abort(),
      onRetry: () =>
        replaceSelected(file, {
          taskKey: job.taskKey,
          position: job.position,
          source: job.source,
        }),
    });
    pending.add(job);
    updatePendingState();
    const activeImage = imageElement(editor, job.position);
    activeImage?.setAttribute("data-image-replacing", "true");
    schedule();
    announce("正在上传替换图片。", "info");
    try {
      const requestUpload = () =>
        uploadMediaFile({
          file,
          url: uploadUrl,
          csrfToken,
          signal: controller.signal,
          onProgress: (value) => uploadTask?.progress(value),
        });
      const { assetId } = await (
        uploadTracker ? uploadTracker.schedule(requestUpload) : requestUpload()
      );
      await refreshLibrary();
      const node = job.removed ? null : editor.state.doc.nodeAt(job.position);
      if (node?.type.name !== "image" || node.attrs.src !== job.source) {
        uploadTask?.success("图片已保留到图片库");
        announce("图片已上传到图片库，原图片位置已发生变化。", "info");
        return;
      }
      job.completing = true;
      dispatchIsolatedEditorTransaction(
        editor,
        editor.state.tr.setNodeMarkup(job.position, undefined, {
          ...node.attrs,
          src: `media:${assetId}`,
        }),
      );
      registerLocalMedia(assetId, file);
      uploadTask?.success("图片已原位替换");
      announce("图片已原位替换。", "success");
    } catch (error) {
      if (
        error instanceof MediaUploadRequestError &&
        error.code === "aborted"
      ) {
        uploadTask?.cancelled("图片替换已取消");
        announce("图片替换已取消。", "info");
      } else {
        const message = imageUploadError(error);
        uploadTask?.error(message);
        announce(message, "error");
      }
    } finally {
      imageElement(editor, job.position)?.removeAttribute("data-image-replacing");
      pending.delete(job);
      updatePendingState();
      replaceInput.value = "";
      schedule();
    }
  };

  const activate = (event) => {
    const button = event.target.closest("[data-image-action]");
    if (!(button instanceof HTMLButtonElement) || !toolbar.contains(button)) return;
    event.preventDefault();
    const action = button.dataset.imageAction;
    if (action === "replace") replaceInput.click();
    if (action === "edit") openDialog();
    if (action === "delete") removeSelected();
  };

  const handleToolbarKey = (event) => {
    if (event.key !== "Escape") return;
    event.preventDefault();
    dismissed = true;
    toolbar.hidden = true;
    editor.view.focus();
  };

  const resetAndSchedule = () => {
    dismissed = false;
    schedule();
  };

  const remapPending = ({ transaction }) => {
    if (!transaction.docChanged) return;
    pending.forEach((job) => {
      if (job.completing || job.removed) return;
      const mapped = transaction.mapping.mapResult(job.position, 1);
      job.position = mapped.pos;
      job.removed = mapped.deleted;
    });
    schedule();
  };

  const beforeUnload = (event) => {
    if (!pending.size) return;
    event.preventDefault();
    event.returnValue = "";
  };

  toolbar.addEventListener("click", activate);
  toolbar.addEventListener("keydown", handleToolbarKey);
  replaceInput.addEventListener("change", () =>
    replaceSelected(replaceInput.files?.[0]),
  );
  dialogForm.addEventListener("submit", applyDialog);
  dialog.querySelector('[data-image-action="close"]').addEventListener(
    "click",
    () => dialog.close("cancelled"),
  );
  dialog.querySelector("[data-image-dialog-cancel]").addEventListener(
    "click",
    () => dialog.close("cancelled"),
  );
  dialog.addEventListener("close", () => {
    restoreSelection();
    schedule();
  });
  editor.on("selectionUpdate", resetAndSchedule);
  editor.on("update", schedule);
  editor.on("transaction", remapPending);
  window.addEventListener("beforeunload", beforeUnload);
  window.addEventListener("resize", schedule);
  window.addEventListener("scroll", schedule, true);
  window.visualViewport?.addEventListener("resize", schedule);
  window.visualViewport?.addEventListener("scroll", schedule);
  schedule();

  return {
    get pendingCount() {
      return pending.size;
    },
    announcePending() {
      announce("请等待替换图片上传完成后再保存。", "warning");
    },
    dispose() {
      if (frame !== null) window.cancelAnimationFrame(frame);
      pending.forEach((job) => job.controller.abort());
      pending.clear();
      toolbar.removeEventListener("click", activate);
      toolbar.removeEventListener("keydown", handleToolbarKey);
      dialogForm.removeEventListener("submit", applyDialog);
      editor.off("selectionUpdate", resetAndSchedule);
      editor.off("update", schedule);
      editor.off("transaction", remapPending);
      window.removeEventListener("beforeunload", beforeUnload);
      window.removeEventListener("resize", schedule);
      window.removeEventListener("scroll", schedule, true);
      window.visualViewport?.removeEventListener("resize", schedule);
      window.visualViewport?.removeEventListener("scroll", schedule);
      toolbar.remove();
      dialog.remove();
      updatePendingState();
    },
  };
}
