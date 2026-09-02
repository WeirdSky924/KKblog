const ACTION_FEEDBACK_DURATION = 1050;
const DOCK_OFFSET = 8;
const READING_LINE_GAP = 16;
const feedbackTimers = new WeakMap();
const articleActionDisposers = new WeakMap();
let bookmarkFailureEventsBound = false;
let likeFailureEventsBound = false;

function announceFeedback(message, { level, key }) {
  document.dispatchEvent(
    new CustomEvent("kaj:feedback", {
      detail: { key, level, message, timeout: 2800 },
    }),
  );
}

function playActionFeedback(shell, action) {
  shell
    .querySelectorAll(`[data-article-action="${action}"]`)
    .forEach((control) => {
      if (!(control instanceof HTMLElement)) return;
      window.clearTimeout(feedbackTimers.get(control));
      control.classList.remove("article-action-button--confirmed");
      void control.offsetWidth;
      control.classList.add("article-action-button--confirmed");
      feedbackTimers.set(
        control,
        window.setTimeout(() => {
          control.classList.remove("article-action-button--confirmed");
          feedbackTimers.delete(control);
        }, ACTION_FEEDBACK_DURATION),
      );
    });
}

function markCopySucceeded(shell) {
  shell.querySelectorAll('[data-article-action="copy"]').forEach((control) => {
    if (!(control instanceof HTMLButtonElement)) return;
    control.dataset.copied = "true";
    control.setAttribute("aria-label", "文章链接已复制，再次点击可复制");
    control.title = "文章链接已复制，再次点击可复制";
  });
}

function fixedHeaderOffset() {
  const siteHeader = document.querySelector("[data-site-header]");
  return siteHeader instanceof HTMLElement
    ? siteHeader.getBoundingClientRect().height + READING_LINE_GAP
    : READING_LINE_GAP;
}

function storedReadingProgress(shell) {
  const raw = shell.dataset.readingBookmarkProgress?.trim();
  if (!raw) return null;
  const progress = Number.parseFloat(raw);
  return Number.isFinite(progress) && progress >= 0 && progress <= 1
    ? progress
    : null;
}

function currentReadingProgress(shell) {
  const prose = shell.querySelector(".article-prose");
  if (!(prose instanceof HTMLElement)) return null;
  const bounds = prose.getBoundingClientRect();
  const proseTop = window.scrollY + bounds.top;
  const readingLine = window.scrollY + fixedHeaderOffset();
  const progress = (readingLine - proseTop) / Math.max(bounds.height, 1);
  return Math.min(1, Math.max(0, progress));
}

function syncReadingBookmarkControls(shell) {
  const progress = storedReadingProgress(shell);
  const hasBookmark = progress !== null;
  shell.querySelectorAll("[data-reading-bookmark-goto]").forEach((control) => {
    if (!(control instanceof HTMLButtonElement)) return;
    control.disabled = !hasBookmark;
    control.title = hasBookmark
      ? "前往上次保存的阅读位置"
      : "尚未保存阅读书签";
  });
  shell.querySelectorAll("[data-reading-bookmark-save]").forEach((control) => {
    if (!(control instanceof HTMLButtonElement)) return;
    control.dataset.saved = String(hasBookmark);
    control.setAttribute(
      "aria-label",
      hasBookmark ? "更新当前阅读位置" : "保存当前阅读位置",
    );
    control.title = hasBookmark ? "更新当前阅读位置" : "保存当前阅读位置";
  });
}

async function saveReadingBookmark(shell, button) {
  const form = button.closest("[data-reading-bookmark-form]");
  const progress = currentReadingProgress(shell);
  if (!(form instanceof HTMLFormElement) || progress === null) return;
  if (form.dataset.submitting === "true") return;

  form.dataset.submitting = "true";
  button.disabled = true;
  const payload = new FormData(form);
  payload.set("progress", progress.toFixed(6));
  try {
    const response = await fetch(form.action, {
      method: "POST",
      body: payload,
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "X-Requested-With": "XMLHttpRequest",
      },
    });
    if (response.redirected) {
      window.location.assign(response.url);
      return;
    }
    const contentType = response.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) {
      throw new Error("reading bookmark response was not JSON");
    }
    const result = await response.json();
    if (!response.ok || result.ok !== true) {
      throw new Error(result.error || "阅读书签保存失败。");
    }
    shell.dataset.readingBookmarkProgress = result.progress;
    const input = form.querySelector("[data-reading-bookmark-input]");
    if (input instanceof HTMLInputElement) input.value = result.progress;
    syncReadingBookmarkControls(shell);
    playActionFeedback(shell, "reading-bookmark");
    announceFeedback(result.created ? "阅读书签已保存。" : "阅读书签已更新。", {
      key: "article-reading-bookmark",
      level: "success",
    });
  } catch (error) {
    announceFeedback(
      error instanceof Error ? error.message : "阅读书签保存失败。",
      { key: "article-reading-bookmark", level: "error" },
    );
  } finally {
    delete form.dataset.submitting;
    button.disabled = false;
  }
}

function scrollToReadingBookmark(shell) {
  const progress = storedReadingProgress(shell);
  const prose = shell.querySelector(".article-prose");
  if (progress === null || !(prose instanceof HTMLElement)) return;
  const bounds = prose.getBoundingClientRect();
  const proseTop = window.scrollY + bounds.top;
  const target = proseTop + bounds.height * progress - fixedHeaderOffset();
  window.scrollTo({
    behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
      ? "auto"
      : "smooth",
    top: Math.max(0, target),
  });
  announceFeedback("已前往阅读书签。", {
    key: "article-reading-bookmark-goto",
    level: "success",
  });
}

function syncBookmarkControls(shell) {
  const source = shell.querySelector(
    "#bookmark-control .bookmark-control__button[aria-pressed]",
  );
  if (!(source instanceof HTMLButtonElement)) return;

  const pressed = source.getAttribute("aria-pressed") === "true";
  shell.querySelectorAll("[data-article-bookmark-mirror]").forEach((mirror) => {
    if (!(mirror instanceof HTMLButtonElement)) return;
    mirror.setAttribute("aria-pressed", String(pressed));
    mirror.setAttribute("aria-label", pressed ? "取消收藏" : "收藏");
    mirror.title = pressed ? "从收藏中移除" : "收藏这篇文章";
    mirror.disabled = false;
  });
}

function syncLikeControl(shell) {
  const form = shell.querySelector("#like-control");
  if (!(form instanceof HTMLFormElement)) return;
  const button = form.querySelector(".article-action-like[aria-pressed]");
  if (button instanceof HTMLButtonElement) button.disabled = false;
  const count = form.dataset.likeCount;
  if (count === undefined) return;
  shell.querySelectorAll("[data-article-like-count]").forEach((target) => {
    target.textContent = count;
  });
}

function bindLikeFailureEvents() {
  if (likeFailureEventsBound) return;
  likeFailureEventsBound = true;

  const restoreLikeControl = (event) => {
    const trigger = event.detail?.elt;
    if (!(trigger instanceof Element)) return;
    const form = trigger.closest("#like-control");
    const shell = form?.closest("[data-article-actions]");
    if (!(form instanceof HTMLFormElement) || !(shell instanceof HTMLElement)) {
      return;
    }
    delete form.dataset.submitting;
    form.removeAttribute("aria-busy");
    form.querySelectorAll("button").forEach((button) => {
      button.removeAttribute("aria-disabled");
      button.disabled = false;
    });
    announceFeedback("点赞操作未完成，请重试。", {
      key: "article-like",
      level: "error",
    });
  };

  document.addEventListener("htmx:sendError", restoreLikeControl);
  document.addEventListener("htmx:responseError", restoreLikeControl);
  document.addEventListener("htmx:timeout", restoreLikeControl);
}

function handleLikeResponse(shell, root) {
  const controls = [];
  if (root instanceof HTMLElement && root.matches("#like-control")) {
    controls.push(root);
  }
  root.querySelectorAll?.("#like-control").forEach((control) => {
    controls.push(control);
  });

  controls.forEach((control) => {
    if (
      !(control instanceof HTMLFormElement) ||
      !shell.contains(control) ||
      control.dataset.articleFeedbackHandled === "true"
    ) {
      return;
    }
    control.dataset.articleFeedbackHandled = "true";
    syncLikeControl(shell);
    if (control.dataset.likeError) {
      announceFeedback(control.dataset.likeError, {
        key: "article-like",
        level: "error",
      });
      return;
    }
    if (!control.classList.contains("like-control--confirmed")) return;
    const liked =
      control.querySelector(".article-action-like")?.getAttribute(
        "aria-pressed",
      ) === "true";
    playActionFeedback(shell, "like");
    announceFeedback(liked ? "文章已点赞。" : "已取消点赞。", {
      key: "article-like",
      level: "success",
    });
  });
}

function bindBookmarkFailureEvents() {
  if (bookmarkFailureEventsBound) return;
  bookmarkFailureEventsBound = true;

  const restoreBookmarkControls = (event) => {
    const trigger = event.detail?.elt;
    if (!(trigger instanceof Element)) return;
    const form = trigger.closest("#bookmark-control");
    const shell = form?.closest("[data-article-actions]");
    if (
      !(form instanceof HTMLFormElement) ||
      !(shell instanceof HTMLElement)
    ) {
      return;
    }
    delete form.dataset.submitting;
    form.removeAttribute("aria-busy");
    form.querySelectorAll("button").forEach((button) => {
      button.removeAttribute("aria-disabled");
    });
    syncBookmarkControls(shell);
    announceFeedback("收藏操作未完成，请重试。", {
      key: "article-bookmark",
      level: "error",
    });
  };

  document.addEventListener("htmx:sendError", restoreBookmarkControls);
  document.addEventListener("htmx:responseError", restoreBookmarkControls);
  document.addEventListener("htmx:timeout", restoreBookmarkControls);
}

function handleBookmarkResponse(shell, root) {
  const controls = [];
  if (root instanceof HTMLElement && root.matches("#bookmark-control")) {
    controls.push(root);
  }
  root.querySelectorAll?.("#bookmark-control").forEach((control) => {
    controls.push(control);
  });

  controls.forEach((control) => {
    if (
      !(control instanceof HTMLFormElement) ||
      !shell.contains(control) ||
      control.dataset.articleFeedbackHandled === "true" ||
      !control.classList.contains("bookmark-control--confirmed")
    ) {
      return;
    }
    control.dataset.articleFeedbackHandled = "true";
    const saved =
      control.querySelector(".bookmark-control__button")?.getAttribute(
        "aria-pressed",
      ) === "true";
    playActionFeedback(shell, "bookmark");
    announceFeedback(saved ? "文章已收藏。" : "已取消收藏。", {
      key: "article-bookmark",
      level: "success",
    });
  });
}

async function copyArticleLink(shell) {
  const url = shell.dataset.articlePermalink;
  const buttons = Array.from(shell.querySelectorAll("[data-copy-link]")).filter(
    (button) => button instanceof HTMLButtonElement,
  );
  if (!url || buttons.length === 0) return;

  buttons.forEach((button) => {
    button.disabled = true;
  });
  try {
    if (!navigator.clipboard) throw new Error("clipboard unavailable");
    await navigator.clipboard.writeText(url);
    markCopySucceeded(shell);
    playActionFeedback(shell, "copy");
    announceFeedback("文章链接已复制。", {
      key: "article-copy",
      level: "success",
    });
  } catch {
    announceFeedback("未能复制，请使用地址栏链接。", {
      key: "article-copy",
      level: "error",
    });
  } finally {
    buttons.forEach((button) => {
      button.disabled = false;
    });
  }
}

function bindArticleActionShell(shell) {
  if (
    !(shell instanceof HTMLElement) ||
    shell.dataset.articleActionsBound === "true"
  ) {
    return;
  }
  const dock = shell.querySelector("[data-article-action-dock]");
  const topActions = shell.querySelector("[data-article-top-actions]");
  const mobileMenu = dock?.querySelector("[data-article-mobile-menu]");
  const mobileMenuToggle = dock?.querySelector(
    "[data-article-mobile-menu-toggle]",
  );
  if (
    !(dock instanceof HTMLElement) ||
    !(topActions instanceof HTMLElement) ||
    !(mobileMenu instanceof HTMLElement) ||
    !(mobileMenuToggle instanceof HTMLButtonElement)
  ) {
    return;
  }

  shell.dataset.articleActionsBound = "true";
  const mobileViewport = window.matchMedia("(max-width: 48rem)");
  const siteHeader = document.querySelector("[data-site-header]");
  const siteFooter = document.querySelector("[data-site-footer]");
  let animationFrame = 0;
  let cleanedUp = false;
  let dockObserver = null;
  let fallbackScrollBound = false;
  let headerHeight = 0;
  let footerOffset = null;
  let handleShellClick;

  const syncActionAccessibility = () => {
    const dockAvailable =
      mobileViewport.matches || dock.dataset.visible === "true";
    const actionsAvailable = mobileViewport.matches
      ? dock.dataset.mobileOpen === "true"
      : dockAvailable;
    dock.setAttribute("aria-hidden", String(!dockAvailable));
    dock.inert = !dockAvailable;
    mobileMenu.setAttribute("aria-hidden", String(!actionsAvailable));
    mobileMenu.inert = !actionsAvailable;
  };

  const setDockVisible = (visible) => {
    const next = String(visible);
    if (dock.dataset.visible === next) return;
    dock.dataset.visible = next;
    syncActionAccessibility();
  };

  const updateHeaderHeight = () => {
    headerHeight =
      siteHeader instanceof HTMLElement
        ? Math.ceil(siteHeader.getBoundingClientRect().height)
        : 0;
  };

  const updateFooterOffset = () => {
    if (!mobileViewport.matches || !(siteFooter instanceof HTMLElement)) return;
    const next = Math.max(
      0,
      Math.ceil(window.innerHeight - siteFooter.getBoundingClientRect().top),
    );
    if (next === footerOffset) return;
    footerOffset = next;
    dock.style.setProperty("--article-action-footer-offset", `${next}px`);
  };

  const updateDockFallback = () => {
    animationFrame = 0;
    if (!shell.isConnected) {
      cleanup();
      return;
    }
    if (mobileViewport.matches) {
      updateFooterOffset();
      return;
    }
    const visible =
      window.scrollY > 0 &&
      topActions.getBoundingClientRect().bottom <= headerHeight + DOCK_OFFSET;
    setDockVisible(visible);
  };

  const queueDockUpdate = () => {
    if (animationFrame === 0) {
      animationFrame = window.requestAnimationFrame(updateDockFallback);
    }
  };

  const bindFallbackScroll = () => {
    if (fallbackScrollBound) return;
    fallbackScrollBound = true;
    window.addEventListener("scroll", queueDockUpdate, { passive: true });
  };

  const unbindFallbackScroll = () => {
    if (!fallbackScrollBound) return;
    fallbackScrollBound = false;
    window.removeEventListener("scroll", queueDockUpdate);
  };

  const setupDockObserver = () => {
    dockObserver?.disconnect();
    dockObserver = null;
    if (mobileViewport.matches) {
      bindFallbackScroll();
      queueDockUpdate();
      return;
    }
    if (!("IntersectionObserver" in window)) {
      bindFallbackScroll();
      queueDockUpdate();
      return;
    }
    unbindFallbackScroll();
    dockObserver = new IntersectionObserver(
      ([entry]) => {
        if (!entry) return;
        setDockVisible(window.scrollY > 0 && !entry.isIntersecting);
      },
      {
        root: null,
        rootMargin: `-${headerHeight + DOCK_OFFSET}px 0px 0px`,
        threshold: 0,
      },
    );
    dockObserver.observe(topActions);
  };

  const setMobileMenu = (open, { returnFocus = false } = {}) => {
    const expanded = mobileViewport.matches && open;
    dock.dataset.mobileOpen = String(expanded);
    mobileMenuToggle.setAttribute("aria-expanded", String(expanded));
    mobileMenuToggle.setAttribute(
      "aria-label",
      expanded ? "收起文章快捷操作" : "展开文章快捷操作",
    );
    mobileMenuToggle.title = expanded
      ? "收起文章快捷操作"
      : "展开文章快捷操作";
    syncActionAccessibility();
    if (returnFocus && mobileViewport.matches) mobileMenuToggle.focus();
  };

  const closeMobileMenuFromOutside = (event) => {
    if (
      dock.dataset.mobileOpen === "true" &&
      event.target instanceof Node &&
      !dock.contains(event.target)
    ) {
      setMobileMenu(false);
    }
  };

  const closeMobileMenuFromKeyboard = (event) => {
    if (event.key !== "Escape" || dock.dataset.mobileOpen !== "true") return;
    event.preventDefault();
    setMobileMenu(false, { returnFocus: true });
  };

  const handleViewportChange = () => {
    setMobileMenu(false);
    updateHeaderHeight();
    setupDockObserver();
    queueDockUpdate();
  };

  const handleWindowResize = () => {
    updateHeaderHeight();
    setupDockObserver();
    queueDockUpdate();
  };

  const cleanup = () => {
    if (cleanedUp) return;
    cleanedUp = true;
    if (animationFrame !== 0) window.cancelAnimationFrame(animationFrame);
    unbindFallbackScroll();
    dockObserver?.disconnect();
    dockObserver = null;
    window.removeEventListener("resize", handleWindowResize);
    document.removeEventListener("click", closeMobileMenuFromOutside);
    document.removeEventListener("keydown", closeMobileMenuFromKeyboard);
    mobileViewport.removeEventListener("change", handleViewportChange);
    if (handleShellClick) shell.removeEventListener("click", handleShellClick);
    shell.removeAttribute("data-article-actions-bound");
    articleActionDisposers.delete(shell);
  };

  handleShellClick = (event) => {
    if (!(event.target instanceof Element)) return;
    if (event.target.closest("[data-article-mobile-menu-toggle]")) {
      event.preventDefault();
      setMobileMenu(dock.dataset.mobileOpen !== "true");
      return;
    }

    const mobileAction = event.target.closest(
      "[data-article-mobile-menu] a, [data-article-mobile-menu] button",
    );
    if (mobileViewport.matches && mobileAction) {
      setMobileMenu(false, { returnFocus: true });
    }

    const mirror = event.target.closest("[data-article-bookmark-mirror]");
    if (mirror instanceof HTMLButtonElement) {
      event.preventDefault();
      const source = shell.querySelector(
        "#bookmark-control .bookmark-control__button[aria-pressed]",
      );
      if (
        source instanceof HTMLButtonElement &&
        source.getAttribute("aria-disabled") !== "true"
      ) {
        mirror.disabled = true;
        source.click();
      }
      return;
    }

    if (event.target.closest("[data-copy-link]")) {
      event.preventDefault();
      void copyArticleLink(shell);
      return;
    }

    const readingBookmark = event.target.closest(
      "[data-reading-bookmark-save]",
    );
    if (readingBookmark instanceof HTMLButtonElement) {
      event.preventDefault();
      void saveReadingBookmark(shell, readingBookmark);
      return;
    }

    if (event.target.closest("[data-reading-bookmark-goto]")) {
      event.preventDefault();
      scrollToReadingBookmark(shell);
      return;
    }

    if (event.target.closest("[data-article-scroll-top]")) {
      event.preventDefault();
      document.getElementById("main-content")?.focus({ preventScroll: true });
      window.scrollTo({
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "auto"
          : "smooth",
        top: 0,
      });
    }
  };

  shell.addEventListener("click", handleShellClick);

  window.addEventListener("resize", handleWindowResize);
  document.addEventListener("click", closeMobileMenuFromOutside);
  document.addEventListener("keydown", closeMobileMenuFromKeyboard);
  mobileViewport.addEventListener("change", handleViewportChange);
  updateHeaderHeight();
  setupDockObserver();
  syncBookmarkControls(shell);
  syncReadingBookmarkControls(shell);
  setMobileMenu(false);
  if (!mobileViewport.matches && !dockObserver) queueDockUpdate();
  articleActionDisposers.set(shell, cleanup);
}

function articleActionShells(root) {
  const shells = new Set();
  if (root instanceof HTMLElement) {
    if (root.matches("[data-article-actions]")) shells.add(root);
    const closest = root.closest("[data-article-actions]");
    if (closest) shells.add(closest);
  }
  root.querySelectorAll?.("[data-article-actions]").forEach((shell) => {
    shells.add(shell);
  });
  return shells;
}

export function initializeArticleActions(root = document) {
  bindBookmarkFailureEvents();
  bindLikeFailureEvents();
  articleActionShells(root).forEach((shell) => {
    bindArticleActionShell(shell);
    syncBookmarkControls(shell);
    syncLikeControl(shell);
    handleBookmarkResponse(shell, root);
    handleLikeResponse(shell, root);
  });
}

export function disposeArticleActions(root = document) {
  articleActionShells(root).forEach((shell) => {
    articleActionDisposers.get(shell)?.();
  });
}
