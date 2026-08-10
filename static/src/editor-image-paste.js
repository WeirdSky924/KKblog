import {
  MediaUploadRequestError,
  uploadMediaFile,
} from "./media-upload.js";
import { editorUploadTrackerFor } from "./editor-upload-state.js";

const MARKDOWN_FORMAT = "MARKDOWN";
const MAX_IMAGES_PER_PASTE = 10;
const PENDING_SOURCE = /^kaj-upload:[0-9a-f-]{36}$/;

function transferImages(transfer) {
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
  const matched = source.value.match(
    new RegExp(`!\\[[^\\]\\r\\n]*\\]\\(${token.replaceAll("-", "\\-")}\\)`),
  );
  if (!matched || matched.index === undefined) return false;
  source.setRangeText(
    replacement,
    matched.index,
    matched.index + matched[0].length,
    "preserve",
  );
  source.dispatchEvent(new Event("input", { bubbles: true }));
  return true;
}

function insertTiptapMarkers(tiptap, jobs, position = null) {
  const content = jobs.map((job) => ({
    type: "image",
    attrs: { src: job.token, alt: "正在上传图片" },
  }));
  const chain = tiptap.chain().focus();
  if (Number.isInteger(position)) chain.insertContentAt(position, content);
  else chain.insertContent(content);
  return chain.run();
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

function setTiptapMarkerLabel(tiptap, token, label) {
  const found = tiptapMarker(tiptap, token);
  if (!found) return false;
  tiptap.view.dispatch(
    tiptap.state.tr
      .setNodeMarkup(found.position, undefined, {
        ...found.node.attrs,
        alt: label,
      })
      .setMeta("addToHistory", false),
  );
  const marker = tiptap.view.dom.querySelector(
    `[data-author-upload-source="${CSS.escape(token)}"]`,
  );
  if (marker instanceof HTMLElement) marker.textContent = label;
  return true;
}

function errorMessage(error, verb) {
  return error instanceof MediaUploadRequestError
    ? `${error.message} 请重新${verb}后重试。`
    : `图片上传失败，请重新${verb}后重试。`;
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
  const uploadTracker = editorUploadTrackerFor(root);
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

  const setMarkerLabel = (token, label) =>
    format === MARKDOWN_FORMAT
      ? replaceMarkdownMarker(source, token, markdownMarker(token).replace("正在上传图片", label))
      : setTiptapMarkerLabel(tiptap, token, label);

  const markerExists = (token) =>
    format === MARKDOWN_FORMAT
      ? source.value.includes(`](${token})`)
      : Boolean(tiptapMarker(tiptap, token));

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
    job.controller = new AbortController();
    const uploadTask = uploadTracker?.begin({
      key: `body-image-${job.token}`,
      label: `正文图片 · ${job.file.name || "粘贴图片"}`,
      onCancel: () => job.controller.abort(),
      onRetry: () => retry(job),
    });
    try {
      const requestUpload = () =>
        uploadMediaFile({
          file: job.file,
          url: uploadUrl,
          csrfToken,
          signal: job.controller.signal,
          onProgress: (value) => uploadTask?.progress(value),
        });
      const { assetId } = await (
        uploadTracker ? uploadTracker.schedule(requestUpload) : requestUpload()
      );
      const inserted = replaceMarker(job.token, assetId);
      if (inserted) registerLocalMedia(assetId, job.file);
      uploadTask?.success(inserted ? "图片已插入正文" : "图片已保留到图片库");
      return { status: inserted ? "inserted" : "retained", assetId };
    } catch (error) {
      const aborted =
        error instanceof MediaUploadRequestError && error.code === "aborted";
      if (format === MARKDOWN_FORMAT) removeMarker(job.token);
      else setMarkerLabel(job.token, aborted ? "图片上传已取消" : "图片上传失败");
      const message = aborted ? "图片上传已取消" : errorMessage(error, job.verb);
      if (aborted) uploadTask?.cancelled(message);
      else uploadTask?.error(message);
      return { status: aborted ? "aborted" : "failed", message };
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

  const retry = (job) => {
    if (disposed || pending.has(job.token)) return;
    if (!markerExists(job.token)) {
      if (format === MARKDOWN_FORMAT) insertMarkdownMarkers(source, [job]);
      else insertTiptapMarkers(tiptap, [job]);
    } else {
      setMarkerLabel(job.token, "正在上传图片");
    }
    pending.set(job.token, job);
    updatePendingState();
    enqueue(job).then(async (result) => {
      if (disposed) return;
      if (["inserted", "retained"].includes(result.status)) {
        await refreshLibrary();
        announce(
          result.status === "inserted"
            ? "图片重试成功并已插入正文。"
            : "图片重试成功并已保留到图片库。",
          "success",
        );
      }
    });
  };

  const insertFiles = (allImages, { position = null, verb = "粘贴" } = {}) => {
    if (disposed) return false;
    if (!allImages.length) return;
    const images = allImages.slice(0, MAX_IMAGES_PER_PASTE);
    const jobs = images.map((file) => ({
      token: pendingSource(),
      file,
      verb,
      controller: null,
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
    } else insertTiptapMarkers(tiptap, jobs, position);
    if (allImages.length > images.length) {
      announce(`一次最多${verb} ${MAX_IMAGES_PER_PASTE} 张图片。`, "warning");
    }
    announce(
      images.length === 1
        ? `正在上传${verb}的图片。`
        : `正在依次上传 ${images.length} 张${verb}图片。`,
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
            : `${failed.length} 张图片上传失败，请重新${verb}后重试。`,
          inserted.length || retained.length ? "warning" : "error",
        );
      } else if (retained.length && !inserted.length) {
        announce(`图片已上传到图片库，${verb}位置已撤销。`, "info");
      } else if (inserted.length) {
        announce(
          inserted.length === 1
            ? `图片已${verb}并插入正文。`
            : `${inserted.length} 张图片已${verb}并插入正文。`,
          "success",
        );
      }
    });
    return true;
  };

  const paste = (event) => {
    const allImages = transferImages(event.clipboardData);
    if (!allImages.length) return;
    event.preventDefault();
    insertFiles(allImages);
  };

  const dragover = (event) => {
    const hasImage = Array.from(event.dataTransfer?.items || []).some(
      (item) => item.kind === "file" && item.type.startsWith("image/"),
    );
    if (!hasImage) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
    target.dataset.imageDropActive = "true";
  };

  const dragleave = (event) => {
    if (event.relatedTarget instanceof Node && target.contains(event.relatedTarget)) {
      return;
    }
    delete target.dataset.imageDropActive;
  };

  const drop = (event) => {
    const allImages = transferImages(event.dataTransfer);
    delete target.dataset.imageDropActive;
    if (!allImages.length) return;
    event.preventDefault();
    const position =
      format === MARKDOWN_FORMAT
        ? null
        : tiptap.view.posAtCoords({ left: event.clientX, top: event.clientY })?.pos;
    insertFiles(allImages, { position, verb: "拖入" });
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
  target.addEventListener("dragover", dragover);
  target.addEventListener("dragleave", dragleave);
  target.addEventListener("drop", drop);
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
      target.removeEventListener("dragover", dragover);
      target.removeEventListener("dragleave", dragleave);
      target.removeEventListener("drop", drop);
      delete target.dataset.imageDropActive;
      if (format === MARKDOWN_FORMAT) {
        target.removeEventListener("input", trackMarkdownInput);
        target.removeEventListener("keydown", undoMarkdownPaste);
      }
      window.removeEventListener("beforeunload", beforeUnload);
      pending.forEach((job) => job.controller?.abort());
      pending.clear();
      updatePendingState();
    },
  };
}

export function isPendingImageSource(value) {
  return PENDING_SOURCE.test(String(value || ""));
}
