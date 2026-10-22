const focusDisposers = new WeakMap();

function boundedInteger(value, minimum, maximum) {
  const parsed = Number.parseInt(value, 10);
  return Number.isInteger(parsed) && parsed >= minimum && parsed <= maximum
    ? parsed
    : null;
}

function formatDuration(milliseconds) {
  const totalSeconds = Math.floor(Math.max(0, milliseconds) / 1000);
  const seconds = String(totalSeconds % 60).padStart(2, "0");
  const totalMinutes = Math.floor(totalSeconds / 60);
  const minutes = String(totalMinutes % 60).padStart(2, "0");
  const hours = Math.floor(totalMinutes / 60);
  return hours > 0
    ? `${hours}:${minutes}:${seconds}`
    : `${String(totalMinutes).padStart(2, "0")}:${seconds}`;
}

function announce(message, level = "warning") {
  document.dispatchEvent(
    new CustomEvent("kaj:feedback", {
      detail: {
        key: "article-focus-mode",
        level,
        message,
        timeout: 5000,
      },
    }),
  );
}

function focusHosts(root) {
  const hosts = new Set();
  if (root instanceof HTMLElement) {
    if (root.matches("[data-article-explanation]")) hosts.add(root);
    const closest = root.closest("[data-article-explanation]");
    if (closest) hosts.add(closest);
  }
  root.querySelectorAll?.("[data-article-explanation]").forEach((host) => {
    hosts.add(host);
  });
  return hosts;
}

function bindArticleFocus(host) {
  if (host.dataset.articleFocusBound === "true") return;
  const toggle = host.querySelector("[data-article-focus-toggle]");
  const pause = host.querySelector("[data-article-focus-pause]");
  const pauseCount = host.querySelector("[data-article-focus-pause-count]");
  const pauseIcon = host.querySelector('[data-article-focus-pause-icon="pause"]');
  const resumeIcon = host.querySelector('[data-article-focus-pause-icon="play"]');
  const toggleLabel = host.querySelector("[data-article-focus-toggle-label]");
  const controls = host.querySelector("[data-article-focus-controls]");
  const timer = host.querySelector("[data-article-focus-timer]");
  const status = host.querySelector("[data-article-focus-status]");
  if (
    !(toggle instanceof HTMLButtonElement) ||
    !(pause instanceof HTMLButtonElement) ||
    !(pauseCount instanceof HTMLElement) ||
    !(pauseIcon instanceof SVGElement) ||
    !(resumeIcon instanceof SVGElement) ||
    !(toggleLabel instanceof HTMLElement) ||
    !(controls instanceof HTMLElement) ||
    !(timer instanceof HTMLElement) ||
    !(status instanceof HTMLElement) ||
    toggle.disabled
  ) {
    return;
  }

  const idleMinutes = boundedInteger(
    toggle.dataset.focusIdleTimeoutMinutes,
    1,
    15,
  );
  const manualPauseLimit = boundedInteger(
    toggle.dataset.focusManualPauseLimit,
    1,
    10,
  );
  if (idleMinutes === null || manualPauseLimit === null) return;

  const idleTimeoutMs = idleMinutes * 60_000;
  let state = "off";
  let elapsedBeforeSegment = 0;
  let segmentStartedAt = null;
  let manualPauseCount = 0;
  let lastActivityAt = 0;
  let renderTimer = 0;
  let idleTimer = 0;
  let hasEnteredFullscreen = false;
  let pendingWarning = "";
  let resumeWhenPageReturns = false;

  const elapsedMilliseconds = () =>
    elapsedBeforeSegment +
    (segmentStartedAt === null ? 0 : performance.now() - segmentStartedAt);

  const render = () => {
    const active = state !== "off";
    const duration = formatDuration(elapsedMilliseconds());
    timer.hidden = !active;
    timer.textContent = duration;
    timer.setAttribute("aria-label", `专注时长 ${duration}`);
    timer.dataset.focusState = state;
    controls.hidden = !active;
    toggle.setAttribute("aria-pressed", String(active));
    toggle.setAttribute("aria-label", active ? "结束专注" : "开启专注模式");
    toggle.title = active ? "结束专注" : "开启专注模式";
    toggleLabel.textContent = active ? "结束专注" : "专注模式";
    pause.hidden = !active;
    pauseIcon.toggleAttribute("hidden", state !== "active");
    resumeIcon.toggleAttribute("hidden", state === "active");
    const pauseAction = state === "active" ? "手动暂停专注" : "继续专注";
    pause.setAttribute("aria-label", pauseAction);
    pause.title = pauseAction;
    pauseCount.textContent = `${manualPauseCount}/${manualPauseLimit}`;
    pauseCount.setAttribute(
      "aria-label",
      `已手动暂停 ${manualPauseCount} 次，共 ${manualPauseLimit} 次`,
    );
    host.dataset.focusActive = String(active);
    const edgeState =
      state === "manual-paused"
        ? "paused"
        : state === "auto-paused"
          ? "warning"
          : "";
    if (edgeState) document.body.dataset.articleFocusEdge = edgeState;
    else delete document.body.dataset.articleFocusEdge;
  };

  const clearTimers = () => {
    window.clearInterval(renderTimer);
    window.clearTimeout(idleTimer);
    renderTimer = 0;
    idleTimer = 0;
  };

  const closeActiveSegment = (closedAt = performance.now()) => {
    if (segmentStartedAt === null) return;
    elapsedBeforeSegment += Math.max(0, closedAt - segmentStartedAt);
    segmentStartedAt = null;
  };

  const updateTimer = () => {
    if (state !== "off") {
      timer.textContent = formatDuration(elapsedMilliseconds());
      timer.setAttribute(
        "aria-label",
        `专注时长 ${formatDuration(elapsedMilliseconds())}`,
      );
    }
  };

  const scheduleIdleTimeout = () => {
    window.clearTimeout(idleTimer);
    if (state !== "active") return;
    const elapsedSinceActivity = performance.now() - lastActivityAt;
    const remaining = Math.max(0, idleTimeoutMs - elapsedSinceActivity);
    idleTimer = window.setTimeout(() => {
      pauseAutomatically(
        `连续 ${idleMinutes} 分钟没有操作，专注计时已暂停。点击“继续”恢复。`,
        { closedAt: lastActivityAt + idleTimeoutMs },
      );
    }, remaining);
  };

  const requestFullscreen = () => {
    if (document.fullscreenElement) {
      hasEnteredFullscreen = true;
      return Promise.resolve(true);
    }
    const element = document.documentElement;
    if (!(element instanceof HTMLElement) || !element.requestFullscreen) {
      return Promise.resolve(false);
    }
    try {
      return Promise.resolve(element.requestFullscreen()).then(
        () => true,
        () => false,
      );
    } catch {
      return Promise.resolve(false);
    }
  };

  const reportFullscreenUnavailable = () => {
    if (state === "off") return;
    const message = "浏览器未能进入全屏，专注模式仍在普通页面继续。";
    status.textContent = message;
    if (document.hidden || !document.hasFocus()) pendingWarning = message;
    else announce(message);
  };

  const beginActiveSegment = () => {
    resumeWhenPageReturns = false;
    state = "active";
    segmentStartedAt = performance.now();
    lastActivityAt = segmentStartedAt;
    render();
    window.clearInterval(renderTimer);
    renderTimer = window.setInterval(updateTimer, 1000);
    scheduleIdleTimeout();
  };

  const endSession = ({ message = "", level = "info", exitFullscreen = true } = {}) => {
    if (state === "off") return;
    closeActiveSegment();
    clearTimers();
    state = "off";
    manualPauseCount = 0;
    pendingWarning = "";
    resumeWhenPageReturns = false;
    hasEnteredFullscreen = false;
    render();
    status.textContent = message;
    if (message) announce(message, level);
    if (exitFullscreen && document.fullscreenElement && document.exitFullscreen) {
      void document.exitFullscreen().catch(() => {});
    }
  };

  function pauseAutomatically(
    message,
    { closedAt, resumeOnReturn = false } = {},
  ) {
    if (state !== "active") return;
    closeActiveSegment(closedAt);
    clearTimers();
    state = "auto-paused";
    resumeWhenPageReturns = resumeOnReturn;
    render();
    status.textContent = message;
    if (document.hidden || !document.hasFocus()) {
      pendingWarning = message;
      return;
    }
    announce(message);
  }

  const resumePendingWarning = () => {
    if (!pendingWarning || document.hidden || !document.hasFocus()) return;
    announce(pendingWarning);
    pendingWarning = "";
  };

  const resumeAfterPageReturn = () => {
    if (state !== "auto-paused" || !resumeWhenPageReturns) {
      resumePendingWarning();
      return;
    }
    if (document.hidden || !document.hasFocus()) return;
    beginActiveSegment();
    pendingWarning = "";
    status.textContent = "页面已恢复焦点，专注计时已继续。";
  };

  const startSession = () => {
    const fullscreenRequest = requestFullscreen();
    manualPauseCount = 0;
    elapsedBeforeSegment = 0;
    status.textContent = "专注模式已开启。切换页面或无操作时会暂停计时。";
    beginActiveSegment();
    announce("专注模式已开启。", "success");
    void fullscreenRequest.then((entered) => {
      if (!entered) reportFullscreenUnavailable();
    });
  };

  const resumeSession = () => {
    const fullscreenRequest = requestFullscreen();
    beginActiveSegment();
    pendingWarning = "";
    status.textContent = "专注计时已继续。";
    announce("专注计时已继续。", "success");
    void fullscreenRequest.then((entered) => {
      if (!entered) reportFullscreenUnavailable();
    });
  };

  const manualPauseOrResume = () => {
    if (state === "active") {
      manualPauseCount += 1;
      if (manualPauseCount >= manualPauseLimit) {
        endSession({
          message: `已手动暂停 ${manualPauseLimit} 次，本次专注已结束。`,
          level: "warning",
        });
        return;
      }
      closeActiveSegment();
      clearTimers();
      state = "manual-paused";
      render();
      const message = `已手动暂停（${manualPauseCount}/${manualPauseLimit}）。点击“继续”恢复。`;
      status.textContent = message;
      announce(message, "info");
      return;
    }
    if (state === "auto-paused" || state === "manual-paused") resumeSession();
  };

  const recordActivity = () => {
    if (state !== "active") return;
    const now = performance.now();
    if (now - lastActivityAt < 1000) return;
    lastActivityAt = now;
    scheduleIdleTimeout();
  };

  const handleWindowBlur = () => {
    pauseAutomatically("页面失去焦点，专注计时已暂停。返回后自动继续。", {
      resumeOnReturn: true,
    });
  };

  const handleVisibilityChange = () => {
    if (document.visibilityState === "hidden") {
      pauseAutomatically("文章页面进入后台，专注计时已暂停。返回后自动继续。", {
        resumeOnReturn: true,
      });
    } else {
      resumeAfterPageReturn();
    }
  };

  const handlePointerOut = (event) => {
    if (
      event.pointerType !== "mouse" ||
      event.relatedTarget !== null ||
      !(event.target instanceof Node) ||
      !document.documentElement.contains(event.target)
    ) {
      return;
    }
    pauseAutomatically("鼠标已移出文章页面，专注计时已暂停。返回后自动继续。", {
      resumeOnReturn: true,
    });
  };

  const handlePointerOver = (event) => {
    if (
      event.pointerType !== "mouse" ||
      event.relatedTarget !== null ||
      !(event.target instanceof Node) ||
      !document.documentElement.contains(event.target)
    ) {
      return;
    }
    resumeAfterPageReturn();
  };

  const handleFullscreenChange = () => {
    if (document.fullscreenElement) {
      hasEnteredFullscreen = true;
      return;
    }
    if (!hasEnteredFullscreen) return;
    hasEnteredFullscreen = false;
    pauseAutomatically("已退出全屏，专注计时已暂停。点击“继续”可重新请求全屏。");
  };

  const handleFocus = () => resumeAfterPageReturn();
  const handlePageHide = () => endSession({ exitFullscreen: false });
  const handleToggle = () => {
    if (state === "off") startSession();
    else endSession({ message: "专注模式已结束。" });
  };

  toggle.addEventListener("click", handleToggle);
  pause.addEventListener("click", manualPauseOrResume);
  document.addEventListener("visibilitychange", handleVisibilityChange);
  document.addEventListener("pointerout", handlePointerOut);
  document.addEventListener("pointerover", handlePointerOver);
  document.addEventListener("fullscreenchange", handleFullscreenChange);
  document.addEventListener("pointermove", recordActivity, { passive: true });
  document.addEventListener("pointerdown", recordActivity, { passive: true });
  document.addEventListener("keydown", recordActivity);
  document.addEventListener("wheel", recordActivity, { passive: true });
  document.addEventListener("touchstart", recordActivity, { passive: true });
  window.addEventListener("blur", handleWindowBlur);
  window.addEventListener("focus", handleFocus);
  window.addEventListener("pagehide", handlePageHide);
  host.dataset.articleFocusBound = "true";
  render();

  focusDisposers.set(host, () => {
    if (state !== "off") endSession({ exitFullscreen: true });
    toggle.removeEventListener("click", handleToggle);
    pause.removeEventListener("click", manualPauseOrResume);
    document.removeEventListener("visibilitychange", handleVisibilityChange);
    document.removeEventListener("pointerout", handlePointerOut);
    document.removeEventListener("pointerover", handlePointerOver);
    document.removeEventListener("fullscreenchange", handleFullscreenChange);
    document.removeEventListener("pointermove", recordActivity);
    document.removeEventListener("pointerdown", recordActivity);
    document.removeEventListener("keydown", recordActivity);
    document.removeEventListener("wheel", recordActivity);
    document.removeEventListener("touchstart", recordActivity);
    window.removeEventListener("blur", handleWindowBlur);
    window.removeEventListener("focus", handleFocus);
    window.removeEventListener("pagehide", handlePageHide);
    delete host.dataset.articleFocusBound;
    focusDisposers.delete(host);
  });
}

export function initializeArticleFocus(root = document) {
  focusHosts(root).forEach(bindArticleFocus);
}

export function disposeArticleFocus(root = document) {
  focusHosts(root).forEach((host) => focusDisposers.get(host)?.());
}
