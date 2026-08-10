export const AUTHOR_EDITOR_PERFORMANCE_BUDGETS = Object.freeze({
  editorUpdateMs: 100,
  previewRequestMs: 2500,
  previewRenderMs: 500,
  uploadQueueMs: 500,
  uploadRequestMs: 60_000,
  uploadConcurrency: 2,
  sampleLimit: 100,
});

const KIND_BUDGETS = Object.freeze({
  editor_update: AUTHOR_EDITOR_PERFORMANCE_BUDGETS.editorUpdateMs,
  preview_request: AUTHOR_EDITOR_PERFORMANCE_BUDGETS.previewRequestMs,
  preview_render: AUTHOR_EDITOR_PERFORMANCE_BUDGETS.previewRenderMs,
  upload_queue: AUTHOR_EDITOR_PERFORMANCE_BUDGETS.uploadQueueMs,
  upload_request: AUTHOR_EDITOR_PERFORMANCE_BUDGETS.uploadRequestMs,
});
const OUTCOMES = new Set(["cancelled", "error", "rejected", "success"]);
const samples = [];

function now() {
  return globalThis.performance?.now?.() ?? Date.now();
}

function duration(value) {
  const normalized = Number(value);
  if (!Number.isFinite(normalized) || normalized < 0) {
    throw new TypeError("editor performance duration must be finite");
  }
  return Math.min(normalized, 3_600_000);
}

export function recordAuthorEditorPerformance(
  kind,
  durationMs,
  { outcome = "success", units = 0 } = {},
) {
  const budgetMs = KIND_BUDGETS[kind];
  if (!Number.isFinite(budgetMs)) throw new TypeError("unknown editor metric kind");
  if (!OUTCOMES.has(outcome)) throw new TypeError("unknown editor metric outcome");
  const normalizedUnits = Math.min(
    Math.max(Math.round(Number(units) || 0), 0),
    1_000_000,
  );
  const normalizedDuration = duration(durationMs);
  const metric = Object.freeze({
    kind,
    durationMs: Number(normalizedDuration.toFixed(3)),
    budgetMs,
    overBudget: normalizedDuration > budgetMs,
    outcome,
    units: normalizedUnits,
  });
  samples.push(metric);
  if (samples.length > AUTHOR_EDITOR_PERFORMANCE_BUDGETS.sampleLimit) {
    samples.splice(0, samples.length - AUTHOR_EDITOR_PERFORMANCE_BUDGETS.sampleLimit);
  }
  if (
    globalThis.document?.dispatchEvent &&
    typeof globalThis.CustomEvent === "function"
  ) {
    globalThis.document.dispatchEvent(
      new CustomEvent("kaj:editor-performance", { detail: metric }),
    );
  }
  return metric;
}

export function authorEditorPerformanceSnapshot() {
  const counts = {};
  const failures = {};
  const overBudget = {};
  samples.forEach((metric) => {
    counts[metric.kind] = (counts[metric.kind] || 0) + 1;
    if (!["success", "cancelled"].includes(metric.outcome)) {
      failures[metric.kind] = (failures[metric.kind] || 0) + 1;
    }
    if (metric.overBudget) {
      overBudget[metric.kind] = (overBudget[metric.kind] || 0) + 1;
    }
  });
  return {
    samples: samples.slice(),
    counts,
    failures,
    overBudget,
  };
}

export function resetAuthorEditorPerformance() {
  samples.length = 0;
}

export function createAuthorUploadScheduler({
  maxConcurrent = AUTHOR_EDITOR_PERFORMANCE_BUDGETS.uploadConcurrency,
} = {}) {
  if (
    !Number.isInteger(maxConcurrent) ||
    maxConcurrent < 1 ||
    maxConcurrent > 4
  ) {
    throw new TypeError("upload concurrency must be between 1 and 4");
  }
  const queue = [];
  let active = 0;
  let disposed = false;

  const drain = () => {
    while (!disposed && active < maxConcurrent && queue.length) {
      const item = queue.shift();
      active += 1;
      recordAuthorEditorPerformance("upload_queue", now() - item.queuedAt);
      const startedAt = now();
      Promise.resolve()
        .then(item.task)
        .then((value) => {
          recordAuthorEditorPerformance("upload_request", now() - startedAt);
          active -= 1;
          drain();
          item.resolve(value);
        })
        .catch((error) => {
          const cancelled =
            error?.name === "AbortError" || error?.code === "aborted";
          recordAuthorEditorPerformance("upload_request", now() - startedAt, {
            outcome: cancelled ? "cancelled" : "error",
          });
          active -= 1;
          drain();
          item.reject(error);
        });
    }
  };

  return {
    schedule(task) {
      if (disposed || typeof task !== "function") {
        return Promise.reject(new TypeError("upload scheduler is unavailable"));
      }
      return new Promise((resolve, reject) => {
        queue.push({ task, resolve, reject, queuedAt: now() });
        drain();
      });
    },
    get state() {
      return { active, queued: queue.length };
    },
    dispose() {
      disposed = true;
      const error = Object.assign(new Error("upload scheduler disposed"), {
        name: "AbortError",
        code: "aborted",
      });
      queue.splice(0).forEach((item) => item.reject(error));
    },
  };
}
