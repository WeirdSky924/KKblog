const EXPLANATION_POLL_MS = 1500;
const STORAGE_VERSION = 1;

function explanationStorageKey(namespace) {
  return `kaj:article-explanation:v${STORAGE_VERSION}:${namespace}`;
}

function explanationCsrf(root) {
  return root.querySelector("input[name='csrfmiddlewaretoken']")?.value || "";
}

function explanationIdempotencyKey() {
  if (typeof globalThis.crypto?.randomUUID === "function") {
    return globalThis.crypto.randomUUID().replaceAll("-", "");
  }
  return `${Date.now()}${Math.random().toString(36).slice(2)}`;
}

function explanationText(root, selector) {
  const element = root.querySelector(selector);
  return element instanceof HTMLInputElement ? element.value : "";
}

function explanationSetText(root, selector, value) {
  const element = root.querySelector(selector);
  if (element instanceof HTMLInputElement) element.value = value;
}

async function explanationJson(response, fallbackMessage) {
  let body = "";
  try {
    body = await response.text();
  } catch {
    const error = new Error(fallbackMessage);
    error.retryable = true;
    throw error;
  }
  try {
    const payload = JSON.parse(body);
    if (!payload || typeof payload !== "object") throw new Error("invalid payload");
    return payload;
  } catch {
    const message =
      response.status === 401 || response.redirected
        ? "登录状态已失效，请重新登录后再试。"
        : response.status === 403
          ? "解释请求被拒绝，请刷新页面后再试。"
          : response.status >= 500
            ? "解释服务暂时不可用，请稍后再试。"
            : fallbackMessage;
    const error = new Error(message);
    error.retryable = response.status >= 500;
    throw error;
  }
}

function explanationReadHistory(key) {
  try {
    const parsed = JSON.parse(localStorage.getItem(key) || "[]");
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (entry) =>
        entry &&
        typeof entry === "object" &&
        typeof entry.id === "string" &&
        typeof entry.articleId === "string",
    );
  } catch {
    return [];
  }
}

function explanationWriteHistory(key, history, limit) {
  const bounded = history.slice(-Math.max(1, limit));
  try {
    localStorage.setItem(key, JSON.stringify(bounded));
  } catch {
    // A disabled or full localStorage must not block the current request.
  }
  return bounded;
}

function explanationSafeHtml(html) {
  if (typeof html !== "string" || !html) return "";
  const template = document.createElement("template");
  template.innerHTML = html;
  const allowed = new Set([
    "A",
    "CODE",
    "DEL",
    "EM",
    "H1",
    "H2",
    "H3",
    "LI",
    "OL",
    "P",
    "PRE",
    "S",
    "STRONG",
    "UL",
  ]);
  template.content.querySelectorAll("*").forEach((node) => {
    if (!(node instanceof HTMLElement)) return;
    if (!allowed.has(node.tagName)) {
      node.replaceWith(...Array.from(node.childNodes));
      return;
    }
    Array.from(node.attributes).forEach((attribute) => {
      if (node.tagName !== "A" || attribute.name !== "href") {
        node.removeAttribute(attribute.name);
      }
    });
    if (node.tagName === "A") {
      const href = node.getAttribute("href") || "";
      if (!/^https?:\/\//i.test(href)) node.removeAttribute("href");
      node.setAttribute("rel", "noopener noreferrer");
      node.setAttribute("target", "_blank");
    }
  });
  return template.innerHTML;
}

function explanationHistoryEntry(entry) {
  const article = document.createElement("article");
  article.className = "article-explanation-entry";
  article.dataset.explanationEntryId = entry.id;
  const meta = document.createElement("div");
  meta.className = "article-explanation-entry__meta";
  const articleId = document.createElement("span");
  articleId.className = "article-explanation-entry__article";
  articleId.textContent = entry.articleId;
  const state = document.createElement("span");
  state.className = "article-explanation-entry__state";
  state.textContent =
    entry.state === "SUCCEEDED"
      ? "已完成"
      : entry.state === "FAILED"
        ? "失败"
        : entry.state === "CANCELLED"
          ? "已停止"
          : entry.state === "RATE_LIMITED"
            ? "次数限制"
            : "生成中";
  meta.append(articleId, state);
  article.append(meta);
  if (entry.selection) {
    const selection = document.createElement("p");
    selection.className = "article-explanation-entry__selection";
    selection.textContent = entry.selection;
    article.append(selection);
  }
  if (entry.wasTruncated) {
    const truncated = document.createElement("p");
    truncated.className = "article-explanation-entry__selection";
    truncated.textContent = `已处理 ${entry.processedCharCount} 字（原选中 ${entry.originalCharCount} 字）。`;
    article.append(truncated);
  }
  if (entry.resultHtml) {
    const result = document.createElement("div");
    result.className = "article-explanation-entry__result";
    result.innerHTML = explanationSafeHtml(entry.resultHtml);
    article.append(result);
  } else if (entry.message) {
    const message = document.createElement("p");
    message.className = "article-explanation-entry__selection";
    message.textContent = entry.message;
    article.append(message);
  }
  const actions = document.createElement("div");
  actions.className = "article-explanation-entry__actions";
  if (
    !entry.stopping &&
    !entry.retrying &&
    ["PENDING", "RUNNING"].includes(entry.state)
  ) {
    const stop = document.createElement("button");
    stop.className = "button button--secondary";
    stop.type = "button";
    stop.dataset.articleExplanationStop = entry.id;
    stop.setAttribute("aria-label", "停止此解释任务");
    stop.textContent = "停止";
    actions.append(stop);
  }
  if (
    entry.retryable &&
    entry.state === "FAILED" &&
    entry.requestId &&
    entry.statusUrl
  ) {
    const retry = document.createElement("button");
    retry.className = "button button--secondary";
    retry.type = "button";
    retry.dataset.articleExplanationRetry = entry.id;
    retry.setAttribute("aria-label", "重试此解释任务");
    retry.textContent = "重试";
    actions.append(retry);
  }
  if (actions.childElementCount > 0) article.append(actions);
  return article;
}

function explanationCurrentHeading(range, body) {
  const headings = Array.from(body.querySelectorAll("h2"));
  let current = "";
  for (const heading of headings) {
    if (!(heading instanceof HTMLElement)) continue;
    const position = range.comparePoint(heading, 0);
    if (position >= 0) current = heading.textContent?.trim() || "";
    else break;
  }
  return current;
}

function explanationRange(root) {
  const selection = window.getSelection();
  if (!selection || selection.rangeCount === 0 || selection.isCollapsed) return null;
  const range = selection.getRangeAt(0);
  const body = root.querySelector("[data-article-explanation-body]");
  if (!(body instanceof HTMLElement)) return null;
  const container = range.commonAncestorContainer;
  const element = container.nodeType === Node.ELEMENT_NODE
    ? container
    : container.parentElement;
  if (!(element instanceof Node) || !body.contains(element)) return null;
  const fragment = range.cloneContents();
  const wrapper = document.createElement("div");
  wrapper.append(fragment);
  const text = selection.toString().trim();
  if (!text || wrapper.querySelector("img")) {
    // Images are stripped by the server; a mixed selection remains valid.
    if (!text) return null;
  }
  return {
    html: wrapper.innerHTML,
    text,
    heading: explanationCurrentHeading(range, body),
    rect: range.getBoundingClientRect(),
  };
}

function explanationSetSelectionButton(root, selection) {
  const button = root.querySelector("[data-article-explanation-selection-action]");
  if (!(button instanceof HTMLElement)) return;
  if (!selection) {
    button.hidden = true;
    return;
  }
  button.hidden = false;
  const rect = selection.rect;
  const buttonRect = button.getBoundingClientRect();
  const margin = 8;
  const gap = 8;
  const width = buttonRect.width || 72;
  const height = buttonRect.height || 44;
  const maxLeft = Math.max(margin, window.innerWidth - width - margin);
  const maxTop = Math.max(margin, window.innerHeight - height - margin);
  const rightSide = rect.right + gap;
  const rightAligned = rect.right - width;
  const left = Math.min(
    Math.max(margin, rightSide <= maxLeft ? rightSide : rightAligned),
    maxLeft,
  );
  const above = rect.top - height - gap;
  const below = rect.bottom + gap;
  const top = above >= margin
    ? above
    : below <= maxTop
      ? below
      : Math.min(Math.max(margin, above), maxTop);
  button.style.left = `${left}px`;
  button.style.top = `${top}px`;
}

function explanationSetStatus(root, message, level = "") {
  const status = root.querySelector("[data-article-explanation-status]");
  if (!(status instanceof HTMLElement)) return;
  status.textContent = message;
  if (level) status.dataset.level = level;
  else delete status.dataset.level;
}

function explanationFormState(root, pending) {
  const submit = root.querySelector("[data-article-explanation-submit]");
  if (submit instanceof HTMLButtonElement) {
    submit.disabled = pending;
    submit.setAttribute("aria-busy", String(pending));
  }
}

export function initializeArticleExplanations(root = document) {
  root.querySelectorAll?.("[data-article-explanation]").forEach((host) => {
    if (!(host instanceof HTMLElement) || host.dataset.explanationBound === "true") return;
    host.dataset.explanationBound = "true";
    const namespace = host.dataset.accountNamespace;
    const articleId = host.dataset.articleId;
    const storageKey = namespace ? explanationStorageKey(namespace) : "";
    const limit = Number.parseInt(host.dataset.historyLimit || "30", 10) || 30;
    let history = storageKey ? explanationReadHistory(storageKey) : [];
    let selection = null;
    let preserveSelection = false;
    const pollTimers = new Map();
    let currentEntry = null;
    let dragState = null;
    const panel = host.querySelector("[data-article-explanation-panel]");
    const bar = host.querySelector("[data-article-reading-tools-bar]");
    const capsule = host.querySelector("[data-article-reading-tools-capsule]");
    const toggle = host.querySelector("[data-article-reading-tools-toggle]");
    const open = host.querySelector("[data-article-explanation-open]");
    const selectionAction = host.querySelector(
      "[data-article-explanation-selection-action]",
    );
    const close = host.querySelector("[data-article-explanation-close]");
    const form = host.querySelector("[data-article-explanation-form]");
    const panelBody = host.querySelector(".article-explanation-panel__body");
    const historyNode = host.querySelector("[data-article-explanation-history]");
    const empty = host.querySelector("[data-article-explanation-empty]");
    if (
      !(panel instanceof HTMLElement) ||
      !(bar instanceof HTMLElement) ||
      !(capsule instanceof HTMLElement) ||
      !(form instanceof HTMLFormElement)
    ) return;

    const persist = () => {
      if (storageKey) history = explanationWriteHistory(storageKey, history, limit);
    };
    const consentKey = storageKey ? `${storageKey}:consent:${articleId}` : "";
    const autoAccept = host.dataset.autoAccept === "true";
    const acceptedForArticle = () => {
      if (autoAccept) return true;
      if (!consentKey) return false;
      try {
        return localStorage.getItem(consentKey) === "accepted";
      } catch {
        return false;
      }
    };
    const consentDialog = host.querySelector("[data-article-explanation-consent]");
    const requestConsent = () => {
      if (acceptedForArticle()) return true;
      if (!(consentDialog instanceof HTMLDialogElement)) {
        return Promise.resolve(false);
      }
      return new Promise((resolve) => {
        const finish = (accepted) => {
          if (consentDialog.open) consentDialog.close();
          if (accepted && consentKey) {
            try {
              localStorage.setItem(consentKey, "accepted");
            } catch {
              // Consent remains valid for this action when storage is unavailable.
            }
          }
          resolve(accepted);
        };
        consentDialog.querySelector("[data-article-explanation-consent-accept]")?.addEventListener(
          "click",
          () => finish(true),
          { once: true },
        );
        consentDialog.querySelector("[data-article-explanation-consent-reject]")?.addEventListener(
          "click",
          () => finish(false),
          { once: true },
        );
        consentDialog.addEventListener("cancel", () => finish(false), { once: true });
        consentDialog.showModal();
      });
    };
    const render = () => {
      if (!(historyNode instanceof HTMLElement)) return;
      historyNode.replaceChildren(...history.map(explanationHistoryEntry));
      if (empty instanceof HTMLElement) empty.hidden = history.length > 0;
      // The newest explanation is the active context. Keep it visible while
      // older entries move out of view inside the panel's own scroll region.
      if (panelBody instanceof HTMLElement) panelBody.scrollTop = panelBody.scrollHeight;
    };
    const openPanel = () => {
      panel.hidden = false;
      if (open instanceof HTMLElement) {
        open.setAttribute("aria-expanded", "true");
        open.setAttribute("aria-label", "关闭划词解释");
        open.setAttribute("title", "关闭划词解释");
      }
      panel.focus({ preventScroll: true });
      requestAnimationFrame(() => {
        if (panelBody instanceof HTMLElement) panelBody.scrollTop = panelBody.scrollHeight;
      });
    };
    const closePanel = ({ focusOpen = false } = {}) => {
      panel.hidden = true;
      if (open instanceof HTMLElement) {
        open.setAttribute("aria-expanded", "false");
        open.setAttribute("aria-label", "打开划词解释");
        open.setAttribute("title", "打开划词解释");
        if (focusOpen) open.focus();
      }
    };
    const clampPanelPosition = (left, top) => {
      const rect = panel.getBoundingClientRect();
      const margin = 8;
      return {
        left: Math.min(Math.max(margin, left), Math.max(margin, window.innerWidth - rect.width - margin)),
        top: Math.min(Math.max(margin, top), Math.max(margin, window.innerHeight - rect.height - margin)),
      };
    };
    const setPanelPosition = (left, top) => {
      const position = clampPanelPosition(left, top);
      panel.style.insetInline = "auto";
      panel.style.insetBlock = "auto";
      panel.style.left = `${position.left}px`;
      panel.style.top = `${position.top}px`;
      panel.style.transform = "none";
    };
    const finishDrag = (event) => {
      if (!dragState || event.pointerId !== dragState.pointerId) return;
      if (panel.hasPointerCapture(event.pointerId)) panel.releasePointerCapture(event.pointerId);
      dragState = null;
      panel.classList.remove("is-dragging");
    };
    const dragHandle = panel.querySelector("[data-article-explanation-drag-handle]");
    dragHandle?.addEventListener("pointerdown", (event) => {
      if (!(event instanceof PointerEvent) || event.button !== 0) return;
      if (event.target instanceof Element && event.target.closest("button, a, input, select, textarea")) return;
      const rect = panel.getBoundingClientRect();
      setPanelPosition(rect.left, rect.top);
      dragState = {
        pointerId: event.pointerId,
        offsetX: event.clientX - rect.left,
        offsetY: event.clientY - rect.top,
      };
      panel.setPointerCapture(event.pointerId);
      panel.classList.add("is-dragging");
      panel.focus({ preventScroll: true });
      event.preventDefault();
    });
    panel.addEventListener("pointermove", (event) => {
      if (!dragState || event.pointerId !== dragState.pointerId) return;
      setPanelPosition(event.clientX - dragState.offsetX, event.clientY - dragState.offsetY);
      event.preventDefault();
    });
    panel.addEventListener("pointerup", finishDrag);
    panel.addEventListener("pointercancel", finishDrag);
    panel.addEventListener("pointerdown", () => panel.focus({ preventScroll: true }));
    window.addEventListener("resize", () => {
      if (!panel.hidden && panel.style.transform === "none") {
        const rect = panel.getBoundingClientRect();
        setPanelPosition(rect.left, rect.top);
      }
    });
    const stopPolling = (entry) => {
      if (!entry?.id) return;
      const timer = pollTimers.get(entry.id);
      if (timer) window.clearTimeout(timer);
      pollTimers.delete(entry.id);
    };
    const schedulePoll = (entry) => {
      if (!entry?.id) return;
      stopPolling(entry);
      const timer = window.setTimeout(() => {
        pollTimers.delete(entry.id);
        void poll(entry);
      }, EXPLANATION_POLL_MS);
      pollTimers.set(entry.id, timer);
    };
    const preserveSelectionStart = () => {
      if (!selection) return;
      preserveSelection = true;
    };
    const preserveSelectionEnd = () => {
      window.setTimeout(() => {
        preserveSelection = false;
      }, 300);
    };
    bar.addEventListener("pointerdown", preserveSelectionStart);
    bar.addEventListener("pointerup", preserveSelectionEnd);
    bar.addEventListener("pointercancel", preserveSelectionEnd);
    selectionAction?.addEventListener("pointerdown", preserveSelectionStart);
    selectionAction?.addEventListener("pointerup", preserveSelectionEnd);
    selectionAction?.addEventListener("pointercancel", preserveSelectionEnd);
    const updateEntry = (entry, payload) => {
      if (!entry) return;
      entry.state = payload.state;
      entry.message = payload.message || "";
      entry.resultHtml = payload.result_html || "";
      entry.retryable = payload.retryable === true;
      entry.originalCharCount = payload.original_char_count || entry.originalCharCount;
      entry.processedCharCount = payload.processed_char_count || entry.processedCharCount;
      entry.wasTruncated = payload.was_truncated === true || entry.wasTruncated;
      entry.stopping = false;
      entry.stopRequested = false;
      entry.retrying = false;
      persist();
      render();
    };
    const poll = async (entry) => {
      if (!entry?.requestId || !entry.statusUrl) return;
      const requestId = entry.requestId;
      const statusUrl = entry.statusUrl;
      const pollGeneration = Number(entry.pollGeneration || 0);
      const isCurrentPoll = () =>
        entry.requestId === requestId &&
        entry.statusUrl === statusUrl &&
        Number(entry.pollGeneration || 0) === pollGeneration;
      try {
        const response = await fetch(statusUrl, {
          credentials: "same-origin",
          headers: { Accept: "application/json" },
        });
        const payload = await explanationJson(response, "状态读取失败，请稍后再试。");
        if (!response.ok || payload.ok !== true) throw new Error(payload.message || "状态读取失败。");
        if (!isCurrentPoll()) return;
        if (payload.request_id && payload.request_id !== requestId) return;
        updateEntry(entry, payload);
        if (["SUCCEEDED", "FAILED", "CANCELLED"].includes(payload.state)) {
          stopPolling(entry);
          if (entry === currentEntry) {
            explanationFormState(host, false);
            explanationSetStatus(host, payload.message || "", payload.state === "FAILED" ? "error" : "");
          }
        } else schedulePoll(entry);
      } catch (error) {
        if (!isCurrentPoll()) return;
        if (entry === currentEntry) {
          explanationSetStatus(host, error instanceof Error ? error.message : "状态读取失败。", "error");
        }
        schedulePoll(entry);
      }
    };

    const selectionKey = (value) =>
      `${value.text}\u0000${value.heading}\u0000${value.html}`;

    const start = async () => {
      if (!selection) return;
      const requestedSelection = selection;
      const requestedSelectionKey = selectionKey(requestedSelection);
      if (
        history.some(
          (entry) =>
            entry.selectionKey === requestedSelectionKey &&
            ["PENDING", "RUNNING"].includes(entry.state),
        )
      ) return;
      if (!(await requestConsent())) {
        explanationSetStatus(host, "你拒绝了本篇文章的划词解释授权。", "error");
        return;
      }
      openPanel();
      const key = explanationIdempotencyKey();
      explanationSetText(host, "[data-explanation-selected-html]", requestedSelection.html);
      explanationSetText(host, "[data-explanation-selected-text]", requestedSelection.text);
      explanationSetText(host, "[data-explanation-section-heading]", requestedSelection.heading);
      explanationSetText(host, "[data-explanation-idempotency-key]", key);
      const entry = {
        id: key,
        requestId: "",
        articleId,
        selectionKey: requestedSelectionKey,
        selection: requestedSelection.text,
        state: "PENDING",
        message: "正在请求解释…",
        resultHtml: "",
        originalCharCount: requestedSelection.text.length,
        processedCharCount: requestedSelection.text.length,
        wasTruncated: false,
        retryable: false,
        pollGeneration: 0,
        stopping: false,
        stopRequested: false,
        retrying: false,
      };
      currentEntry = entry;
      history.push(entry);
      persist();
      render();
      explanationFormState(host, true);
      explanationSetStatus(host, "正在请求解释…");
      const body = new FormData(form);
      try {
        const response = await fetch(host.dataset.createUrl || "", {
          method: "POST",
          body,
          credentials: "same-origin",
          headers: {
            Accept: "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "X-CSRFToken": explanationCsrf(host),
          },
        });
        const payload = await explanationJson(response, "解释请求失败，请稍后再试。");
        if (!response.ok || payload.ok !== true) {
          entry.state = entry.stopRequested
            ? "CANCELLED"
            : payload.status_name === "rate_limited"
              ? "RATE_LIMITED"
              : "FAILED";
          entry.message = entry.stopRequested
            ? "已停止。"
            : payload.message || "解释请求失败。";
          entry.retryable = false;
          entry.stopping = false;
          entry.stopRequested = false;
          persist();
          render();
          if (entry === currentEntry) {
            explanationFormState(host, false);
            explanationSetStatus(host, entry.message, "error");
          }
          return;
        }
        entry.requestId = payload.request_id;
        entry.statusUrl = `${host.dataset.createUrl}${payload.request_id}/`;
        entry.state = payload.state || "PENDING";
        entry.originalCharCount = payload.original_char_count || entry.originalCharCount;
        entry.processedCharCount = payload.processed_char_count || entry.processedCharCount;
        entry.wasTruncated = payload.was_truncated === true;
        if (entry.stopRequested) {
          entry.stopping = false;
          void stop(entry.id);
          return;
        }
        persist();
        render();
        schedulePoll(entry);
      } catch (error) {
        entry.state = entry.stopRequested ? "CANCELLED" : "FAILED";
        entry.message = entry.stopRequested
          ? "已停止。"
          : error instanceof Error
            ? error.message
            : "解释请求失败。";
        entry.retryable = entry.stopRequested
          ? false
          : error?.retryable === true || error instanceof TypeError;
        entry.stopping = false;
        entry.stopRequested = false;
        persist();
        render();
        if (entry === currentEntry) {
          explanationFormState(host, false);
          explanationSetStatus(host, entry.message, "error");
        }
      }
    };

    const stop = async (entryId) => {
      const entry = history.find((item) => item.id === entryId);
      if (!entry || !["PENDING", "RUNNING"].includes(entry.state)) return;
      if (entry.stopping) return;
      if (!entry.requestId || !entry.statusUrl) {
        entry.stopping = true;
        entry.stopRequested = true;
        entry.message = "正在停止…";
        persist();
        render();
        if (entry === currentEntry) {
          explanationFormState(host, false);
          explanationSetStatus(host, "停止请求已提交。", "info");
        }
        return;
      }
      const requestId = entry.requestId;
      const statusUrl = entry.statusUrl;
      entry.pollGeneration = Number(entry.pollGeneration || 0) + 1;
      entry.stopping = true;
      entry.message = "正在停止…";
      persist();
      render();
      try {
        const response = await fetch(`${statusUrl}cancel/`, {
          method: "POST",
          credentials: "same-origin",
          headers: { Accept: "application/json", "X-CSRFToken": explanationCsrf(host) },
        });
        const payload = await explanationJson(response, "停止失败，请稍后再试。");
        if (!response.ok || payload.ok !== true) throw new Error(payload.message || "停止失败。");
        if (entry.requestId !== requestId || entry.statusUrl !== statusUrl) {
          entry.stopping = false;
          persist();
          render();
          return;
        }
        updateEntry(entry, payload);
        stopPolling(entry);
        if (entry === currentEntry) {
          explanationFormState(host, false);
          explanationSetStatus(host, payload.message || "已停止。", "info");
        }
      } catch (error) {
        entry.stopping = false;
        persist();
        render();
        if (entry === currentEntry) {
          explanationSetStatus(host, error instanceof Error ? error.message : "停止失败。", "error");
        }
      }
    };

    const retry = async (entryId) => {
      const failed = history.find((entry) => entry.id === entryId);
      if (!failed || !failed.retryable) return;
      if (!failed.requestId || !failed.statusUrl || failed.retrying) return;
      failed.retryable = false;
      failed.message = "正在重试…";
      failed.state = "PENDING";
      failed.retrying = true;
      failed.pollGeneration = Number(failed.pollGeneration || 0) + 1;
      currentEntry = failed;
      stopPolling(failed);
      persist();
      render();
      explanationFormState(host, true);
      try {
        const body = new FormData();
        body.set("idempotency_key", `${failed.id}:retry`);
        const response = await fetch(`${failed.statusUrl}retry/`, {
          method: "POST",
          body,
          credentials: "same-origin",
          headers: { Accept: "application/json", "X-CSRFToken": explanationCsrf(host) },
        });
        const payload = await explanationJson(response, "重试失败，请稍后再试。");
        if (!response.ok || payload.ok !== true) throw new Error(payload.message || "重试失败。");
        failed.requestId = payload.request_id;
        failed.statusUrl = `${host.dataset.createUrl}${payload.request_id}/`;
        failed.state = payload.state || "PENDING";
        failed.retrying = false;
        schedulePoll(failed);
      } catch (error) {
        failed.state = "FAILED";
        failed.retrying = false;
        failed.retryable = error?.retryable === true || error instanceof TypeError;
        failed.message = error instanceof Error ? error.message : "重试失败。";
        if (failed === currentEntry) explanationFormState(host, false);
      }
      persist();
      render();
    };

    toggle?.addEventListener("click", () => {
      const expanded = toggle.getAttribute("aria-expanded") === "true";
      const nextExpanded = !expanded;
      toggle.setAttribute("aria-expanded", String(nextExpanded));
      toggle.setAttribute(
        "aria-label",
        nextExpanded ? "收起文章阅读工具" : "展开文章阅读工具",
      );
      toggle.setAttribute(
        "title",
        nextExpanded ? "收起文章阅读工具" : "展开文章阅读工具",
      );
      capsule.hidden = !nextExpanded;
      bar.classList.toggle("is-expanded", nextExpanded);
    });
    open?.addEventListener("click", () => {
      if (panel.hidden) openPanel();
      else closePanel();
    });
    close?.addEventListener("click", () => closePanel({ focusOpen: true }));
    host.querySelector("[data-article-explanation-clear]")?.addEventListener("click", () => {
      if (!window.confirm("清空当前账户的划词解释历史？")) return;
      history = [];
      persist();
      render();
    });
    selectionAction?.addEventListener("click", start);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      start();
    });
    host.addEventListener("click", (event) => {
      const target = event.target instanceof Element ? event.target.closest("[data-article-explanation-retry]") : null;
      if (target instanceof HTMLElement) {
        retry(target.dataset.articleExplanationRetry || "");
        return;
      }
      const stopTarget = event.target instanceof Element
        ? event.target.closest("[data-article-explanation-stop]")
        : null;
      if (stopTarget instanceof HTMLElement) {
        stop(stopTarget.dataset.articleExplanationStop || "");
      }
    });
    document.addEventListener("selectionchange", () => {
      // The article body lives beside the fixed reading-tools aside, not
      // inside it. Resolve the selection against the document so selections
      // in the public article can reach the server-side context validator.
      const next = explanationRange(document);
      if (
        !next &&
        selection &&
        (preserveSelection || host.contains(document.activeElement))
      ) return;
      selection = next;
      explanationSetSelectionButton(host, next);
    });
    render();
    const pendingEntries = history.filter(
      (entry) =>
        ["PENDING", "RUNNING"].includes(entry.state) && entry.requestId && entry.statusUrl,
    );
    const pending = pendingEntries.at(-1);
    if (pending) {
      currentEntry = pending;
      explanationFormState(host, true);
    }
    pendingEntries.forEach(schedulePoll);
  });
}
