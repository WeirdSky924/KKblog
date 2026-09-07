const ASSET_ID = /^[0-9A-HJKMNP-TV-Z]{26}$/;
// Keep the browser deadline aligned with the reverse proxy's 120-second
// upstream window. Disk fsync can briefly wait behind a PostgreSQL checkpoint.
const UPLOAD_TIMEOUT_MS = 120_000;

export class MediaUploadRequestError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "MediaUploadRequestError";
    this.code = code;
  }
}

function uploadEndpoint(value, label) {
  try {
    const endpoint = new URL(value, window.location.href);
    if (endpoint.origin !== window.location.origin) {
      throw new Error("cross-origin upload");
    }
    return endpoint.href;
  } catch {
    throw new MediaUploadRequestError(
      "invalid_endpoint",
      `${label}上传地址无效，请刷新页面后重试。`,
    );
  }
}

function uploadResponse(source) {
  const template = document.createElement("template");
  template.innerHTML = String(source || "").trim();
  const node = template.content.querySelector("[data-media-upload-result]");
  const assetId = node?.dataset.assetId || "";
  const message = node?.querySelector(".field-error")?.textContent?.trim() || "";
  return {
    assetId: ASSET_ID.test(assetId) ? assetId : "",
    message,
  };
}

export function uploadMediaFile({
  file,
  url,
  csrfToken = "",
  mediaLabel = "图片",
  onProgress = null,
  signal = null,
}) {
  const label =
    mediaLabel === "附件"
      ? "附件"
      : mediaLabel === "知识文档"
        ? "知识文档"
        : mediaLabel === "主视觉媒体"
          ? "主视觉媒体"
          : "图片";
  if (!(file instanceof File)) {
    return Promise.reject(
      new MediaUploadRequestError("invalid_file", `没有可上传的${label}。`),
    );
  }

  let endpoint;
  try {
    endpoint = uploadEndpoint(url, label);
  } catch (error) {
    return Promise.reject(error);
  }

  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new MediaUploadRequestError("aborted", `${label}上传已取消。`));
      return;
    }
    const request = new XMLHttpRequest();
    const body = new FormData();
    body.append("file", file, file.name || "clipboard-image");
    let settled = false;

    const finish = (callback) => {
      if (settled) return;
      settled = true;
      signal?.removeEventListener?.("abort", abort);
      callback();
    };
    const fail = (code, message) => {
      finish(() => reject(new MediaUploadRequestError(code, message)));
    };
    const abort = () => {
      if (settled) return;
      request.abort();
      fail("aborted", `${label}上传已取消。`);
    };

    signal?.addEventListener?.("abort", abort, { once: true });
    request.open("POST", endpoint);
    request.timeout = UPLOAD_TIMEOUT_MS;
    request.setRequestHeader("X-Requested-With", "XMLHttpRequest");
    if (csrfToken) request.setRequestHeader("X-CSRFToken", csrfToken);
    request.upload.addEventListener("progress", (event) => {
      if (typeof onProgress !== "function") return;
      onProgress(
        event.lengthComputable
          ? Math.min(Math.max(Math.round((event.loaded / event.total) * 100), 0), 100)
          : 0,
      );
    });
    request.addEventListener("load", () => {
      const response = uploadResponse(request.responseText);
      if (request.status === 201 && response.assetId) {
        finish(() => resolve({ assetId: response.assetId }));
        return;
      }
      fail(
        "rejected",
        response.message || `${label}上传未完成，请重试。`,
      );
    });
    request.addEventListener("error", () => {
      fail("network", `网络异常，${label}上传失败，请重试。`);
    });
    request.addEventListener("timeout", () => {
      fail("timeout", `${label}上传超时，请重试。`);
    });
    try {
      request.send(body);
    } catch {
      fail("network", `${label}上传失败，请重试。`);
    }
  });
}
