const ACTION_FEEDBACK_DURATION = 1050;
const DOCK_OFFSET = 8;
const feedbackTimers = new WeakMap();
let bookmarkFailureEventsBound = false;

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
  if (
    !(dock instanceof HTMLElement) ||
    !(topActions instanceof HTMLElement)
  ) {
    return;
  }

  shell.dataset.articleActionsBound = "true";
  let animationFrame = 0;

  const updateDock = () => {
    animationFrame = 0;
    if (!shell.isConnected) {
      window.removeEventListener("scroll", queueDockUpdate);
      window.removeEventListener("resize", queueDockUpdate);
      return;
    }
    const siteHeader = document.querySelector("[data-site-header]");
    const headerHeight =
      siteHeader instanceof HTMLElement
        ? siteHeader.getBoundingClientRect().height
        : 0;
    const visible =
      window.scrollY > 0 &&
      topActions.getBoundingClientRect().bottom <= headerHeight + DOCK_OFFSET;
    if (dock.dataset.visible === String(visible)) return;
    dock.dataset.visible = String(visible);
    dock.setAttribute("aria-hidden", String(!visible));
    dock.inert = !visible;
  };

  const queueDockUpdate = () => {
    if (animationFrame === 0) {
      animationFrame = window.requestAnimationFrame(updateDock);
    }
  };

  shell.addEventListener("click", (event) => {
    if (!(event.target instanceof Element)) return;
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
  });

  window.addEventListener("scroll", queueDockUpdate, { passive: true });
  window.addEventListener("resize", queueDockUpdate);
  syncBookmarkControls(shell);
  updateDock();
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
  articleActionShells(root).forEach((shell) => {
    bindArticleActionShell(shell);
    syncBookmarkControls(shell);
    handleBookmarkResponse(shell, root);
  });
}
