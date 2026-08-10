import { CircleX, RotateCw, X, createIcons } from "lucide";

import { createAuthorUploadScheduler } from "./editor-performance.js";

export const EDITOR_UPLOAD_STATES = Object.freeze([
  "pending",
  "success",
  "error",
  "cancelled",
]);

const trackers = new WeakMap();

export function transitionEditorUploadState(current, event, value = 0) {
  if (current === null && event === "start") {
    return { state: "pending", progress: 0 };
  }
  if (current?.state === "pending") {
    if (event === "progress") {
      return {
        state: "pending",
        progress: Math.min(Math.max(Math.round(Number(value) || 0), 0), 100),
      };
    }
    if (event === "success") return { state: "success", progress: 100 };
    if (event === "error") return { state: "error", progress: current.progress };
    if (event === "cancel") {
      return { state: "cancelled", progress: current.progress };
    }
  }
  if (["error", "cancelled"].includes(current?.state) && event === "retry") {
    return { state: "pending", progress: 0 };
  }
  throw new Error("invalid editor upload transition");
}

function element(tag, { className, text, attributes = {} } = {}) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  Object.entries(attributes).forEach(([name, item]) =>
    node.setAttribute(name, item),
  );
  return node;
}

function iconButton(action, label, icon) {
  const button = element("button", {
    className: "author-upload-task__action",
    attributes: { type: "button", "aria-label": label, title: label },
  });
  button.dataset.uploadAction = action;
  button.append(element("i", { attributes: { "data-lucide": icon } }));
  return button;
}

function renderTray() {
  const tray = element("section", {
    className: "author-upload-tray",
    attributes: { "aria-label": "上传队列", "aria-live": "polite" },
  });
  tray.dataset.editorUploadTray = "";
  tray.hidden = true;
  const header = element("header");
  header.append(
    element("strong", { text: "上传队列" }),
    element("span", { attributes: { "data-upload-summary": "" } }),
  );
  const list = element("ol", { attributes: { "data-upload-list": "" } });
  tray.append(header, list);
  return tray;
}

function renderTask(record) {
  const item = element("li", {
    className: "author-upload-task",
    attributes: { "data-upload-state": record.status.state },
  });
  item.dataset.uploadKey = record.key;
  const heading = element("div", { className: "author-upload-task__heading" });
  const label = element("strong", { text: record.label });
  const output = element("output", { attributes: { "data-upload-status": "" } });
  heading.append(label, output);
  const progress = element("progress", {
    attributes: { max: "100", value: String(record.status.progress) },
  });
  const actions = element("div", { className: "author-upload-task__actions" });
  actions.append(
    iconButton("cancel", "取消上传", "circle-x"),
    iconButton("retry", "重试上传", "rotate-cw"),
    iconButton("dismiss", "关闭上传状态", "x"),
  );
  item.append(heading, progress, actions);
  return item;
}

function statusText(record) {
  if (record.message) return record.message;
  return {
    pending: `${record.status.progress}%`,
    success: "上传完成",
    error: "上传失败",
    cancelled: "已取消",
  }[record.status.state];
}

function createTracker(root) {
  const tray = renderTray();
  const list = tray.querySelector("[data-upload-list]");
  const summary = tray.querySelector("[data-upload-summary]");
  document.body.append(tray);
  const records = new Map();
  const scheduler = createAuthorUploadScheduler();
  let disposed = false;

  const updateRoot = () => {
    const pending = Array.from(records.values()).filter(
      (record) => record.status.state === "pending",
    ).length;
    if (pending) root.dataset.editorUploadCount = String(pending);
    else delete root.dataset.editorUploadCount;
    summary.textContent = pending ? `${pending} 项进行中` : "";
    tray.hidden = records.size === 0;
  };

  const render = (record) => {
    let item = list.querySelector(`[data-upload-key="${CSS.escape(record.key)}"]`);
    if (!item) {
      item = renderTask(record);
      list.append(item);
      createIcons({
        root: item,
        icons: { CircleX, RotateCw, X },
        attrs: { "aria-hidden": "true", focusable: "false" },
      });
    }
    item.dataset.uploadState = record.status.state;
    item.querySelector("progress").value = record.status.progress;
    item.querySelector("[data-upload-status]").textContent = statusText(record);
    item.querySelector('[data-upload-action="cancel"]').hidden =
      record.status.state !== "pending";
    item.querySelector('[data-upload-action="retry"]').hidden =
      !["error", "cancelled"].includes(record.status.state);
    item.querySelector('[data-upload-action="dismiss"]').hidden =
      record.status.state === "pending";
    updateRoot();
  };

  const remove = (key) => {
    const record = records.get(key);
    if (!record) return;
    window.clearTimeout(record.removeTimer);
    records.delete(key);
    list.querySelector(`[data-upload-key="${CSS.escape(key)}"]`)?.remove();
    updateRoot();
  };

  const begin = ({ key, label, onCancel = null, onRetry = null }) => {
    if (disposed || !key || !label) return null;
    let record = records.get(key);
    if (record && ["error", "cancelled"].includes(record.status.state)) {
      record.status = transitionEditorUploadState(record.status, "retry");
    } else if (!record || record.status.state === "success") {
      if (record) remove(key);
      record = {
        key,
        label,
        status: transitionEditorUploadState(null, "start"),
        message: "",
        onCancel,
        onRetry,
        removeTimer: null,
      };
      records.set(key, record);
    }
    record.label = label;
    record.message = "";
    record.onCancel = onCancel;
    record.onRetry = onRetry;
    render(record);

    const transition = (event, message = "") => {
      if (!records.has(key) || record.status.state !== "pending") return;
      record.status = transitionEditorUploadState(record.status, event);
      record.message = message;
      render(record);
      if (event === "success") {
        record.removeTimer = window.setTimeout(() => remove(key), 3200);
      }
    };
    return {
      progress(value) {
        if (record.status.state !== "pending") return;
        record.status = transitionEditorUploadState(
          record.status,
          "progress",
          value,
        );
        render(record);
      },
      success(message = "上传完成") {
        transition("success", message);
      },
      error(message = "上传失败") {
        transition("error", message);
      },
      cancelled(message = "上传已取消") {
        transition("cancel", message);
      },
      remove: () => remove(key),
    };
  };

  const activate = (event) => {
    const button = event.target.closest("[data-upload-action]");
    const item = button?.closest("[data-upload-key]");
    const record = item ? records.get(item.dataset.uploadKey) : null;
    if (!(button instanceof HTMLButtonElement) || !record) return;
    if (button.dataset.uploadAction === "cancel") record.onCancel?.();
    if (button.dataset.uploadAction === "retry") record.onRetry?.();
    if (button.dataset.uploadAction === "dismiss") remove(record.key);
  };

  const beforeUnload = (event) => {
    if (!Array.from(records.values()).some((item) => item.status.state === "pending")) {
      return;
    }
    event.preventDefault();
    event.returnValue = "";
  };
  tray.addEventListener("click", activate);
  window.addEventListener("beforeunload", beforeUnload);

  return {
    begin,
    schedule: (task) => scheduler.schedule(task),
    get schedulerState() {
      return scheduler.state;
    },
    get pendingCount() {
      return Array.from(records.values()).filter(
        (record) => record.status.state === "pending",
      ).length;
    },
    announcePending() {
      document.dispatchEvent(
        new CustomEvent("kaj:feedback", {
          detail: {
            key: "author-upload-pending",
            level: "warning",
            message: "请等待上传完成或取消上传后再保存。",
            timeout: 5000,
          },
        }),
      );
    },
    dispose() {
      disposed = true;
      records.forEach((record) => {
        window.clearTimeout(record.removeTimer);
        if (record.status.state === "pending") record.onCancel?.();
      });
      records.clear();
      scheduler.dispose();
      tray.removeEventListener("click", activate);
      window.removeEventListener("beforeunload", beforeUnload);
      tray.remove();
      delete root.dataset.editorUploadCount;
      trackers.delete(root);
    },
  };
}

export function editorUploadTrackerFor(scope) {
  const root = scope?.matches?.("form[data-author-editor]")
    ? scope
    : scope?.closest?.("form[data-author-editor]");
  if (!(root instanceof HTMLFormElement)) return null;
  if (!trackers.has(root)) trackers.set(root, createTracker(root));
  return trackers.get(root);
}

export function disposeEditorUploadTracker(scope) {
  const root = scope?.matches?.("form[data-author-editor]")
    ? scope
    : scope?.closest?.("form[data-author-editor]");
  trackers.get(root)?.dispose();
}
