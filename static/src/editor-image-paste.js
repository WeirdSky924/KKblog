import {
  MediaUploadRequestError,
  uploadMediaFile,
} from "./media-upload.js";

const MARKDOWN_FORMAT = "MARKDOWN";
const MAX_IMAGES_PER_PASTE = 10;
const PENDING_SOURCE = /^kaj-upload:[0-9a-f-]{36}$/;

function clipboardImages(event) {
  const transfer = event.clipboardData;
  if (!transfer) return [];
  const fromItems = Array.from(transfer.items || [])
    .filter((item) => item.kind === "file" && item.type.startsWith("image/"))
    .map((item) => item.getAsFile())
    .filter((file) => file instanceof File);
  const candidates = fromItems.length ? fromItems : Array.from(transfer.files || []);
  return candidates.filter(
    (file) => file instanceof File && file.type.startsWith("image/"),
  );
}

function pendingSource() {
  return `kaj-upload:${crypto.randomUUID()}`;
}

function markdownMarker(token) {
  return `![正在上传图片](${token})`;
}

function insertMarkdownMarkers(source, jobs) {
  const start = source.selectionStart;
  const end = source.selectionEnd;
  const before = source.value.slice(0, start);
  const after = source.value.slice(end);
  const content = jobs.map((job) => markdownMarker(job.token)).join("\n\n");
  const insertion = `${before && !before.endsWith("\n") ? "\n" : ""}${content}${
    after && !after.startsWith("\n") ? "\n" : ""
  }`;
  source.setRangeText(insertion, start, end, "end");
  source.dispatchEvent(new Event("input", { bubbles: true }));
}

function replaceMarkdownMarker(source, token, replacement) {
  const marker = markdownMarker(token);
  const start = source.value.indexOf(marker);
  if (start < 0) return false;
  source.setRangeText(replacement, start, start + marker.length, "preserve");
  source.dispatchEvent(new Event("input", { bubbles: true }));
  return true;
}

function insertTiptapMarkers(tiptap, jobs) {
  return tiptap
    .chain()
    .focus()
    .insertContent(
      jobs.map((job) => ({
        type: "image",
        attrs: { src: job.token, alt: "正在上传图片" },
      })),
    )
    .run();
}

function tiptapMarker(tiptap, token) {
  let found = null;
  tiptap.state.doc.descendants((node, position) => {
    if (found || node.type.name !== "image" || node.attrs.src !== token) return;
    found = { node, position };
  });
  return found;
}

function replaceTiptapMarker(tiptap, token, assetId) {
  const found = tiptapMarker(tiptap, token);
  if (!found) return false;
  const transaction = tiptap.state.tr
    .setNodeMarkup(found.position, undefined, {
      ...found.node.attrs,
      src: `media:${assetId}`,
      alt: "正文图片",
    })
    .setMeta("addToHistory", false);
  tiptap.view.dispatch(transaction);
  return true;
}

function removeTiptapMarker(tiptap, token) {
  const found = tiptapMarker(tiptap, token);
  if (!found) return false;
  const transaction = tiptap.state.tr
    .delete(found.position, found.position + found.node.nodeSize)
    .setMeta("addToHistory", false);
  tiptap.view.dispatch(transaction);
  return true;
}

function errorMessage(error) {
  return error instanceof MediaUploadRequestError
    ? `${error.message} 请重新粘贴后重试。`
    : "图片上传失败，请重新粘贴后重试。";
}

export function initializeEditorImagePaste({
  root,
  source,
  format,
  tiptap,
  announce,
  registerLocalMedia,
  refreshLibrary,
}) {
  const picker = root.querySelector('[data-media-picker="article-body"]');
  const uploadUrl = picker?.dataset.mediaUploadUrl || "";
  const csrfToken = picker?.querySelector("input[name='csrfmiddlewaretoken']")?.value || "";
  const target = format === MARKDOWN_FORMAT ? source : tiptap?.view?.dom;
  if (!(target instanceof HTMLElement) || !uploadUrl || !csrfToken) return null;

  const pending = new Map();
  let queue = Promise.resolve();
  let disposed = false;
  let markdownUndo = null;

  const updatePendingState = () => {
    if (pending.size) root.dataset.pasteUploadCount = String(pending.size);
    else delete root.dataset.pasteUploadCount;
  };

  const replaceMarker = (token, assetId) =>
    format === MARKDOWN_FORMAT
      ? replaceMarkdownMarker(source, token, `![正文图片](media:${assetId})`)
      : replaceTiptapMarker(tiptap, token, assetId);

  const removeMarker = (token) =>
    format === MARKDOWN_FORMAT
      ? replaceMarkdownMarker(source, token, "")
      : removeTiptapMarker(tiptap, token);

  const containsAsset = (assetId) => {
    const reference = `media:${assetId}`;
    if (format === MARKDOWN_FORMAT) return source.value.includes(reference);
    let found = false;
    tiptap.state.doc.descendants((node) => {
      if (node.type.name === "image" && node.attrs.src === reference) found = true;
    });
    return found;
  };

  const uploadJob = async (job) => {
    try {
      const { assetId } = await uploadMediaFile({
        file: job.file,
        url: uploadUrl,
        csrfToken,
        signal: job.controller.signal,
      });
      const inserted = replaceMarker(job.token, assetId);
      if (inserted) registerLocalMedia(assetId, job.file);
      return { status: inserted ? "inserted" : "retained", assetId };
    } catch (error) {
      removeMarker(job.token);
      return {
        status: error instanceof MediaUploadRequestError && error.code === "aborted"
          ? "aborted"
          : "failed",
        message: errorMessage(error),
      };
    } finally {
      pending.delete(job.token);
      updatePendingState();
    }
  };

  const enqueue = (job) => {
    const result = queue.then(() => uploadJob(job));
    queue = result.then(() => undefined, () => undefined);
    return result;
  };

  const paste = (event) => {
    if (disposed) return;
    const allImages = clipboardImages(event);
    if (!allImages.length) return;
    event.preventDefault();
    const images = allImages.slice(0, MAX_IMAGES_PER_PASTE);
    const jobs = images.map((file) => ({
      token: pendingSource(),
      file,
      controller: new AbortController(),
    }));
    jobs.forEach((job) => pending.set(job.token, job));
    updatePendingState();
    if (format === MARKDOWN_FORMAT) {
      markdownUndo = {
        value: source.value,
        start: source.selectionStart,
        end: source.selectionEnd,
        tokens: jobs.map((job) => job.token),
      };
      insertMarkdownMarkers(source, jobs);
    } else insertTiptapMarkers(tiptap, jobs);
    if (allImages.length > images.length) {
      announce(`一次最多粘贴 ${MAX_IMAGES_PER_PASTE} 张图片。`, "warning");
    }
    announce(
      images.length === 1
        ? "正在上传粘贴的图片。"
        : `正在依次上传 ${images.length} 张粘贴图片。`,
      "info",
    );
    Promise.all(jobs.map(enqueue)).then(async (results) => {
      if (disposed) return;
      const uploaded = results.filter((item) =>
        ["inserted", "retained"].includes(item.status),
      );
      if (uploaded.length) await refreshLibrary();
      const inserted = uploaded.filter((item) => containsAsset(item.assetId));
      const retained = uploaded.filter((item) => !containsAsset(item.assetId));
      const failed = results.filter((item) => item.status === "failed");
      if (failed.length) {
        announce(
          failed.length === 1
            ? failed[0].message
            : `${failed.length} 张图片上传失败，请重新粘贴后重试。`,
          inserted.length || retained.length ? "warning" : "error",
        );
      } else if (retained.length && !inserted.length) {
        announce("图片已上传到图片库，粘贴位置已撤销。", "info");
      } else if (inserted.length) {
        announce(
          inserted.length === 1
            ? "图片已粘贴并插入正文。"
            : `${inserted.length} 张图片已粘贴并插入正文。`,
          "success",
        );
      }
    });
  };

  const trackMarkdownInput = (event) => {
    if (event.isTrusted) markdownUndo = null;
  };
  const undoMarkdownPaste = (event) => {
    if (
      !markdownUndo ||
      event.altKey ||
      event.shiftKey ||
      !(event.ctrlKey || event.metaKey) ||
      event.key.toLowerCase() !== "z"
    ) {
      return;
    }
    event.preventDefault();
    const uploadPending = markdownUndo.tokens.some((token) => pending.has(token));
    const { value, start, end } = markdownUndo;
    markdownUndo = null;
    source.value = value;
    source.dispatchEvent(new Event("input", { bubbles: true }));
    source.setSelectionRange(start, end);
    announce(
      uploadPending
        ? "已撤销粘贴位置，上传完成后图片仍会保留在图片库。"
        : "粘贴位置已撤销，图片仍保留在图片库。",
      "info",
    );
  };

  const beforeUnload = (event) => {
    if (!pending.size) return;
    event.preventDefault();
    event.returnValue = "";
  };
  target.addEventListener("paste", paste, true);
  if (format === MARKDOWN_FORMAT) {
    target.addEventListener("input", trackMarkdownInput);
    target.addEventListener("keydown", undoMarkdownPaste);
  }
  window.addEventListener("beforeunload", beforeUnload);

  return {
    get pendingCount() {
      return pending.size;
    },
    announcePending() {
      announce("请等待粘贴图片上传完成后再保存。", "warning");
    },
    dispose() {
      disposed = true;
      target.removeEventListener("paste", paste, true);
      if (format === MARKDOWN_FORMAT) {
        target.removeEventListener("input", trackMarkdownInput);
        target.removeEventListener("keydown", undoMarkdownPaste);
      }
      window.removeEventListener("beforeunload", beforeUnload);
      pending.forEach((job) => job.controller.abort());
      pending.clear();
      updatePendingState();
    },
  };
}

export function isPendingImageSource(value) {
  return PENDING_SOURCE.test(String(value || ""));
}
