const PREFERENCE_KEY = "kajspace:article-reader:v1";
const MIN_FONT_SIZE = 15;
const MAX_FONT_SIZE = 25;
const DEFAULT_PREFERENCES = { mode: "scroll", theme: "day", fontSize: 17 };
const VALID_MODES = new Set(["scroll", "horizontal", "vertical"]);
const VALID_THEMES = new Set(["day", "eye-care", "dark"]);
const disposers = new WeakMap();

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function readPreferences() {
  try {
    const stored = JSON.parse(window.localStorage.getItem(PREFERENCE_KEY) || "null");
    return {
      mode: VALID_MODES.has(stored?.mode) ? stored.mode : DEFAULT_PREFERENCES.mode,
      theme: VALID_THEMES.has(stored?.theme) ? stored.theme : DEFAULT_PREFERENCES.theme,
      fontSize: clamp(
        Number.isFinite(stored?.fontSize) ? stored.fontSize : DEFAULT_PREFERENCES.fontSize,
        MIN_FONT_SIZE,
        MAX_FONT_SIZE,
      ),
    };
  } catch {
    return { ...DEFAULT_PREFERENCES };
  }
}

function articleReaderShells(root) {
  const shells = new Set();
  if (root instanceof HTMLElement) {
    if (root.matches("[data-article-actions]")) shells.add(root);
    const closest = root.closest("[data-article-actions]");
    if (closest) shells.add(closest);
  }
  root.querySelectorAll?.("[data-article-actions]").forEach((shell) => shells.add(shell));
  return shells;
}

function bindArticleReader(shell) {
  if (shell.dataset.articleReaderBound === "true") return;
  const openButton = shell.querySelector("[data-article-reader-open]");
  const prose = shell.querySelector(".article-prose");
  const dialog = document.querySelector("[data-article-reader-mode]");
  const viewport = dialog?.querySelector("[data-reader-viewport]");
  const contentHost = dialog?.querySelector("[data-reader-content]");
  const closeButton = dialog?.querySelector("[data-reader-close]");
  const progressOutput = dialog?.querySelector("[data-reader-progress]");
  const fontOutput = dialog?.querySelector("[data-reader-font-value]");
  const header = dialog?.querySelector(".article-reader-mode__header");
  const options = dialog?.querySelector(".article-reader-mode__options");
  const surface = dialog?.querySelector(".article-reader-mode__surface");
  if (
    !(openButton instanceof HTMLButtonElement) ||
    !(prose instanceof HTMLElement) ||
    !(dialog instanceof HTMLDialogElement) ||
    !(viewport instanceof HTMLElement) ||
    !(contentHost instanceof HTMLElement) ||
    !(closeButton instanceof HTMLButtonElement) ||
    !(progressOutput instanceof HTMLOutputElement) ||
    !(fontOutput instanceof HTMLOutputElement) ||
    !(header instanceof HTMLElement) ||
    !(options instanceof HTMLElement) ||
    !(surface instanceof HTMLElement)
  ) return;

  shell.dataset.articleReaderBound = "true";
  const mobileViewport = window.matchMedia("(max-width: 48rem)");
  const preferences = readPreferences();
  let mode = preferences.mode;
  let pageIndex = 0;
  let pageCount = 1;
  let savedScrollY = 0;
  let articleProgress = 0;
  let originalParent = null;
  let originalNextSibling = null;
  let placeholder = null;
  let contentMoved = false;
  let resizeFrame = 0;
  let progressFrame = 0;
  let swipeStart = null;
  let settingsVisible = true;
  let suppressClickUntil = 0;
  let cleanedUp = false;

  const persist = () => {
    try {
      window.localStorage.setItem(PREFERENCE_KEY, JSON.stringify(preferences));
    } catch {
      // Reading remains available when browser storage is disabled.
    }
  };

  const progress = () => {
    if (mode === "horizontal" || mode === "vertical") {
      return pageCount <= 1 ? 0 : pageIndex / (pageCount - 1);
    }
    const maxScroll = Math.max(0, viewport.scrollHeight - viewport.clientHeight);
    return maxScroll === 0 ? 0 : clamp(viewport.scrollTop / maxScroll, 0, 1);
  };

  const syncSettingsVisibility = () => {
    dialog.dataset.readerSettings = settingsVisible ? "visible" : "hidden";
    header.inert = !settingsVisible;
    options.inert = !settingsVisible;
    viewport.setAttribute(
      "aria-label",
      mode === "horizontal"
        ? settingsVisible
          ? "文章内容；左右点击翻页，中央点击收起设置"
          : "文章内容；左侧上一页，右侧下一页，中央显示设置；按 Enter 切换设置"
        : mode === "vertical"
          ? settingsVisible
            ? "文章内容；上划下一页，下划上一页；点击收起设置"
            : "文章内容；上划下一页，下划上一页；点击显示设置"
          : "文章内容；上下滚动阅读",
    );
  };

  const setSettingsVisible = (visible, { preserveProgress = true } = {}) => {
    const isPagedMode = mode === "horizontal" || mode === "vertical";
    const nextVisible = isPagedMode ? visible : true;
    if (settingsVisible === nextVisible) return;
    const currentProgress = progress();
    settingsVisible = nextVisible;
    syncSettingsVisibility();
    if (!settingsVisible && (header.contains(document.activeElement) || options.contains(document.activeElement))) {
      viewport.focus({ preventScroll: true });
    }
    window.requestAnimationFrame(() => {
      if (dialog.open) seek(preserveProgress ? currentProgress : articleProgress);
    });
  };

  const updateProgress = () => {
    if (!dialog.open) return;
    if (mode === "horizontal") {
      progressOutput.value = `第 ${pageIndex + 1} / ${pageCount} 页`;
      progressOutput.textContent = progressOutput.value;
      return;
    }
    if (mode === "vertical") {
      progressOutput.value = `第 ${pageIndex + 1} / ${pageCount} 页`;
      progressOutput.textContent = progressOutput.value;
      return;
    }
    const maxScroll = Math.max(0, viewport.scrollHeight - viewport.clientHeight);
    const percent = Math.round((maxScroll === 0 ? 0 : viewport.scrollTop / maxScroll) * 100);
    progressOutput.value = `阅读进度 ${percent}%`;
    progressOutput.textContent = progressOutput.value;
  };

  const measurePages = () => {
    if (mode === "horizontal") {
      const pageWidth = Math.max(1, contentHost.clientWidth);
      prose.style.setProperty("--reader-page-width", `${pageWidth}px`);
      prose.style.width = `${pageWidth}px`;
      const currentTransform = prose.style.transform;
      prose.style.transform = "none";
      const fullWidth = Math.max(pageWidth, prose.scrollWidth);
      prose.style.transform = currentTransform;
      pageCount = Math.max(1, Math.ceil(fullWidth / pageWidth));
      pageIndex = clamp(pageIndex, 0, pageCount - 1);
      prose.style.transform = `translate3d(-${pageIndex * pageWidth}px, 0, 0)`;
      return;
    }
    prose.style.removeProperty("--reader-page-width");
    prose.style.removeProperty("width");
    prose.style.removeProperty("transform");
    if (mode === "vertical") {
      const maxScroll = Math.max(0, viewport.scrollHeight - viewport.clientHeight);
      pageCount = Math.max(1, Math.ceil(maxScroll / Math.max(1, viewport.clientHeight)) + 1);
      pageIndex = clamp(pageIndex, 0, pageCount - 1);
      return;
    }
    pageCount = 1;
    pageIndex = 0;
  };

  const seek = (ratio) => {
    measurePages();
    const targetProgress = clamp(ratio, 0, 1);
    if (mode === "horizontal") {
      pageIndex = Math.round(targetProgress * (pageCount - 1));
      measurePages();
    } else if (mode === "vertical") {
      const step = Math.max(1, viewport.clientHeight);
      pageIndex = Math.round(targetProgress * (pageCount - 1));
      const maxScroll = Math.max(0, viewport.scrollHeight - viewport.clientHeight);
      viewport.scrollTo({ top: Math.min(pageIndex * step, maxScroll), behavior: "auto" });
    } else {
      const maxScroll = Math.max(0, viewport.scrollHeight - viewport.clientHeight);
      viewport.scrollTo({ top: maxScroll * targetProgress, behavior: "auto" });
    }
    updateProgress();
  };

  const applyMode = (nextMode, { preserveProgress = true, persistChange = true } = {}) => {
    if (!VALID_MODES.has(nextMode)) return;
    const oldProgress = progress();
    mode = nextMode;
    preferences.mode = nextMode;
    viewport.dataset.readerMode = mode;
    dialog.dataset.readerMode = mode;
    if (mode === "horizontal") {
      prose.dataset.readerPresentation = "horizontal";
      contentHost.style.height = "100%";
      viewport.scrollTop = 0;
    } else {
      delete prose.dataset.readerPresentation;
      contentHost.style.removeProperty("height");
      settingsVisible = true;
    }
    syncSettingsVisibility();
    dialog.querySelectorAll("[data-reader-mode-option]").forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.readerModeOption === mode));
    });
    if (persistChange) persist();
    window.requestAnimationFrame(() => {
      if (!dialog.open) return;
      seek(preserveProgress ? oldProgress : articleProgress);
    });
  };

  const applyTheme = (theme, persistChange = true) => {
    if (!VALID_THEMES.has(theme)) return;
    preferences.theme = theme;
    surface.dataset.readerTheme = theme;
    surface.dataset.theme = theme === "day" ? "light" : theme;
    dialog.querySelectorAll("[data-reader-theme-option]").forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.readerThemeOption === theme));
    });
    if (persistChange) persist();
  };

  const applyFontSize = (size, persistChange = true) => {
    const oldProgress = dialog.open ? progress() : 0;
    preferences.fontSize = clamp(size, MIN_FONT_SIZE, MAX_FONT_SIZE);
    prose.style.setProperty("--reader-font-size", `${preferences.fontSize}px`);
    fontOutput.value = `${preferences.fontSize}px`;
    fontOutput.textContent = fontOutput.value;
    dialog.querySelectorAll("[data-reader-font-step]").forEach((button) => {
      const step = Number(button.dataset.readerFontStep);
      button.disabled = step < 0
        ? preferences.fontSize <= MIN_FONT_SIZE
        : preferences.fontSize >= MAX_FONT_SIZE;
    });
    if (persistChange) persist();
    if (!dialog.open) return;
    window.requestAnimationFrame(() => {
      if (!dialog.open) return;
      seek(oldProgress);
    });
  };

  const navigate = (direction) => {
    if (mode === "horizontal") {
      pageIndex = clamp(pageIndex + direction, 0, pageCount - 1);
      measurePages();
      updateProgress();
      return;
    }
    if (mode === "vertical") {
      const step = Math.max(1, viewport.clientHeight);
      const maxScroll = Math.max(0, viewport.scrollHeight - viewport.clientHeight);
      pageIndex = clamp(pageIndex + direction, 0, pageCount - 1);
      viewport.scrollTo({ top: Math.min(pageIndex * step, maxScroll), behavior: "smooth" });
      updateProgress();
      return;
    }
    viewport.scrollBy({ top: direction * viewport.clientHeight * 0.78, behavior: "smooth" });
  };

  const handleOpen = () => {
    if (!mobileViewport.matches || dialog.open || !prose.isConnected) return;
    savedScrollY = window.scrollY;
    const bounds = prose.getBoundingClientRect();
    const readingPoint = window.scrollY + Math.min(window.innerHeight * 0.18, 144);
    articleProgress = clamp((readingPoint - (window.scrollY + bounds.top)) / Math.max(bounds.height, 1), 0, 1);
    originalParent = prose.parentNode;
    originalNextSibling = prose.nextSibling;
    placeholder = document.createElement("div");
    placeholder.className = "article-reader-mode__placeholder";
    placeholder.style.height = `${Math.max(1, Math.ceil(bounds.height))}px`;
    placeholder.setAttribute("aria-hidden", "true");
    originalParent.replaceChild(placeholder, prose);
    contentHost.append(prose);
    contentMoved = true;
    applyTheme(preferences.theme, false);
    applyFontSize(preferences.fontSize, false);
    try {
      dialog.showModal();
    } catch {
      restoreArticle();
      return;
    }
    settingsVisible = true;
    syncSettingsVisibility();
    applyMode(preferences.mode, { preserveProgress: false, persistChange: false });
    window.requestAnimationFrame(() => viewport.focus({ preventScroll: true }));
  };

  const handleOpenClick = (event) => {
    if (
      event.target instanceof Element &&
      event.target.closest("[data-article-reader-open]")
    ) handleOpen();
  };

  const restoreArticle = () => {
    if (!contentMoved) return;
    if (placeholder?.isConnected) {
      placeholder.replaceWith(prose);
    } else if (originalParent?.isConnected && prose.parentNode === contentHost) {
      originalParent.insertBefore(prose, originalNextSibling?.parentNode === originalParent ? originalNextSibling : null);
    }
    placeholder = null;
    originalParent = null;
    originalNextSibling = null;
    contentMoved = false;
    window.requestAnimationFrame(() => window.scrollTo(0, savedScrollY));
  };

  const handleClose = () => {
    restoreArticle();
  };

  const handleModeClick = (event) => {
    if (!(event.target instanceof Element)) return;
    const button = event.target.closest("[data-reader-mode-option]");
    if (button instanceof HTMLButtonElement) applyMode(button.dataset.readerModeOption);
  };

  const handleThemeClick = (event) => {
    if (!(event.target instanceof Element)) return;
    const button = event.target.closest("[data-reader-theme-option]");
    if (button instanceof HTMLButtonElement) applyTheme(button.dataset.readerThemeOption);
  };

  const handleFontClick = (event) => {
    if (!(event.target instanceof Element)) return;
    const button = event.target.closest("[data-reader-font-step]");
    if (button instanceof HTMLButtonElement) {
      applyFontSize(preferences.fontSize + Number(button.dataset.readerFontStep));
    }
  };

  const handleAnchorClick = (event) => {
    if (!(event.target instanceof Element)) return;
    const link = event.target.closest("a[href^='#']");
    if (!(link instanceof HTMLAnchorElement)) return;
    let targetId;
    try {
      targetId = decodeURIComponent(link.hash.slice(1));
    } catch {
      return;
    }
    const target = targetId ? prose.querySelector(`#${CSS.escape(targetId)}`) : null;
    if (!(target instanceof HTMLElement)) return;
    event.preventDefault();
    const details = link.closest("details");
    if (details instanceof HTMLDetailsElement) details.open = false;
    applyMode("scroll");
    window.requestAnimationFrame(() => {
      const offset = target.getBoundingClientRect().top - viewport.getBoundingClientRect().top;
      viewport.scrollTo({ top: viewport.scrollTop + offset - 16, behavior: "smooth" });
    });
  };

  const handleScroll = () => {
    if (progressFrame === 0) {
      progressFrame = window.requestAnimationFrame(() => {
        progressFrame = 0;
        updateProgress();
      });
    }
  };

  const handleTouchStart = (event) => {
    if (!VALID_MODES.has(mode) || mode === "scroll" || event.touches.length !== 1) return;
    swipeStart = { x: event.touches[0].clientX, y: event.touches[0].clientY };
  };

  const handleTouchEnd = (event) => {
    if (!swipeStart || event.changedTouches.length !== 1) return;
    const touch = event.changedTouches[0];
    const dx = touch.clientX - swipeStart.x;
    const dy = touch.clientY - swipeStart.y;
    swipeStart = null;
    const horizontalSwipe =
      mode === "horizontal" && Math.abs(dx) >= 42 && Math.abs(dx) >= Math.abs(dy) * 1.2;
    const verticalSwipe =
      mode === "vertical" && Math.abs(dy) >= 42 && Math.abs(dy) >= Math.abs(dx) * 1.2;
    if (!horizontalSwipe && !verticalSwipe) return;
    event.preventDefault();
    suppressClickUntil = Date.now() + 700;
    navigate(horizontalSwipe ? (dx < 0 ? 1 : -1) : (dy < 0 ? 1 : -1));
    setSettingsVisible(false);
  };

  const handleReaderTap = (event) => {
    if ((mode !== "horizontal" && mode !== "vertical") || !dialog.open) return;
    if (Date.now() < suppressClickUntil) {
      event.preventDefault();
      event.stopPropagation();
      return;
    }
    if (!(event.target instanceof Element)) return;
    if (event.target.closest("a, button, input, textarea, select, summary, video[controls], audio[controls]")) return;
    if (window.getSelection()?.isCollapsed === false) return;
    if (mode === "vertical") {
      setSettingsVisible(!settingsVisible);
      return;
    }
    const bounds = viewport.getBoundingClientRect();
    const relativeX = event.clientX - bounds.left;
    if (relativeX < bounds.width / 3) {
      navigate(-1);
      setSettingsVisible(false);
    } else if (relativeX >= (bounds.width * 2) / 3) {
      navigate(1);
      setSettingsVisible(false);
    } else {
      setSettingsVisible(!settingsVisible);
    }
  };

  const handleResize = () => {
    if (!dialog.open || resizeFrame !== 0) return;
    const oldProgress = progress();
    resizeFrame = window.requestAnimationFrame(() => {
      resizeFrame = 0;
      if (dialog.open) seek(oldProgress);
    });
  };

  const handleNavigation = (event) => {
    if (event.target !== viewport) return;
    if (mode === "horizontal" && (event.key === "Enter" || event.key === " ")) {
      event.preventDefault();
      setSettingsVisible(!settingsVisible);
      return;
    }
    if (event.key === "ArrowLeft" && mode === "horizontal") {
      event.preventDefault();
      navigate(-1);
      setSettingsVisible(false);
    } else if (event.key === "ArrowRight" && mode === "horizontal") {
      event.preventDefault();
      navigate(1);
      setSettingsVisible(false);
    } else if (event.key === "ArrowUp" && mode === "vertical") {
      event.preventDefault();
      navigate(-1);
    } else if (event.key === "ArrowDown" && mode === "vertical") {
      event.preventDefault();
      navigate(1);
    }
  };

  const cleanup = () => {
    if (cleanedUp) return;
    cleanedUp = true;
    if (dialog.open) dialog.close();
    restoreArticle();
    if (resizeFrame !== 0) window.cancelAnimationFrame(resizeFrame);
    if (progressFrame !== 0) window.cancelAnimationFrame(progressFrame);
    shell.removeEventListener("click", handleOpenClick);
    closeButton.removeEventListener("click", close);
    dialog.removeEventListener("close", handleClose);
    dialog.removeEventListener("click", handleModeClick);
    dialog.removeEventListener("click", handleThemeClick);
    dialog.removeEventListener("click", handleFontClick);
    dialog.removeEventListener("click", handleAnchorClick);
    viewport.removeEventListener("click", handleReaderTap);
    dialog.removeEventListener("keydown", handleNavigation);
    viewport.removeEventListener("scroll", handleScroll);
    viewport.removeEventListener("touchstart", handleTouchStart);
    viewport.removeEventListener("touchend", handleTouchEnd);
    window.removeEventListener("resize", handleResize);
    delete shell.dataset.articleReaderBound;
    disposers.delete(shell);
  };

  const close = () => dialog.close();
  shell.addEventListener("click", handleOpenClick);
  closeButton.addEventListener("click", close);
  dialog.addEventListener("close", handleClose);
  dialog.addEventListener("click", handleModeClick);
  dialog.addEventListener("click", handleThemeClick);
  dialog.addEventListener("click", handleFontClick);
  dialog.addEventListener("click", handleAnchorClick);
  viewport.addEventListener("click", handleReaderTap);
  dialog.addEventListener("keydown", handleNavigation);
  viewport.addEventListener("scroll", handleScroll, { passive: true });
  viewport.addEventListener("touchstart", handleTouchStart, { passive: true });
  viewport.addEventListener("touchend", handleTouchEnd, { passive: false });
  window.addEventListener("resize", handleResize, { passive: true });
  applyTheme(preferences.theme, false);
  applyFontSize(preferences.fontSize, false);
  disposers.set(shell, cleanup);
};

export function initializeArticleReaderMode(root = document) {
  articleReaderShells(root).forEach(bindArticleReader);
}

export function disposeArticleReaderMode(root = document) {
  articleReaderShells(root).forEach((shell) => disposers.get(shell)?.());
}
