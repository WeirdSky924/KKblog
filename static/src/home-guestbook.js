const boundGuestbookShells = new WeakSet();
let globalGuestbookEventsBound = false;
let pendingGuestbookState = null;
let guestbookLayoutFrame = 0;
let guestbookBoundsObserver = null;

function guestbookShellFromSwap(event) {
  const candidate = event.detail?.target ?? event.detail?.root;
  if (candidate instanceof HTMLElement && candidate.id) {
    const current = document.getElementById(candidate.id);
    if (current instanceof HTMLElement) return current;
  }
  if (candidate instanceof HTMLElement) {
    const shell = candidate.matches("[data-home-guestbook-shell]")
      ? candidate
      : candidate.querySelector("[data-home-guestbook-shell]");
    if (shell instanceof HTMLElement) return shell;
  }
  return document.querySelector("[data-home-guestbook-shell]");
}

function syncGuestbookBounds(shell) {
  const panel = shell.querySelector("[data-home-guestbook-panel]");
  const page = shell.closest("[data-home-page]");
  const header = document.querySelector("[data-site-header]");
  const heroContent = page?.querySelector(".home-hero__content");
  if (
    !(panel instanceof HTMLElement) ||
    !(page instanceof HTMLElement) ||
    !(header instanceof HTMLElement) ||
    !(heroContent instanceof HTMLElement)
  ) {
    return;
  }

  // The page survives HTMX replacement of the guestbook shell.
  const previousWidth = page.style.getPropertyValue("--home-guestbook-width");
  const previousHeight = page.style.getPropertyValue("--home-guestbook-height");
  const headerBottom = Math.max(0, header.getBoundingClientRect().bottom);
  const heroContentTop = Math.min(
    window.innerHeight,
    heroContent.getBoundingClientRect().top,
  );
  const safeBottom = Math.max(headerBottom, heroContentTop);
  const safeHeight = safeBottom - headerBottom;
  page.style.removeProperty("--home-guestbook-width");
  page.style.removeProperty("--home-guestbook-height");
  const baseWidth = panel.offsetWidth;
  const baseHeight = panel.offsetHeight;
  if (baseWidth <= 0 || baseHeight <= 0) {
    if (previousWidth) page.style.setProperty("--home-guestbook-width", previousWidth);
    if (previousHeight) page.style.setProperty("--home-guestbook-height", previousHeight);
    return;
  }

  const rightInset = Number.parseFloat(getComputedStyle(panel).insetInlineEnd) || 0;
  const leftInset = window.matchMedia("(max-width: 63.99rem)").matches ? 8 : 16;
  const pageBounds = page.getBoundingClientRect();
  const safeWidth = Math.max(
    0,
    pageBounds.right - rightInset - pageBounds.left - leftInset,
  );
  const boundsReady = safeHeight >= 180 && safeWidth >= 240;
  const width = boundsReady ? Math.min(baseWidth * 2, safeWidth) : 0;
  const height = boundsReady ? Math.min(baseHeight * 2, safeHeight) : 0;
  page.style.setProperty(
    "--home-guestbook-center",
    `${headerBottom + safeHeight / 2}px`,
  );
  page.style.setProperty("--home-guestbook-width", `${width}px`);
  page.style.setProperty("--home-guestbook-height", `${height}px`);
  shell.dataset.boundsReady = String(boundsReady);
  if (!boundsReady) setCollapsed(shell, true);
  else if (
    shell.dataset.manuallyCollapsed !== "true" &&
    shell.dataset.articlesVisible !== "true"
  ) {
    setCollapsed(shell, false);
  }
  const openButton = shell.querySelector("[data-home-guestbook-open]");
  if (openButton instanceof HTMLButtonElement) {
    const label = boundsReady ? "展开留言板" : "返回大图留言板";
    openButton.setAttribute("aria-label", label);
    openButton.title = label;
  }
}

function scheduleGuestbookBounds() {
  if (guestbookLayoutFrame) return;
  guestbookLayoutFrame = window.requestAnimationFrame(() => {
    guestbookLayoutFrame = 0;
    const shell = document.querySelector("[data-home-guestbook-shell]");
    if (shell instanceof HTMLElement) syncGuestbookBounds(shell);
  });
}

function setCollapsed(shell, collapsed) {
  const panel = shell.querySelector("[data-home-guestbook-panel]");
  const openButton = shell.querySelector("[data-home-guestbook-open]");
  const collapseButton = shell.querySelector("[data-home-guestbook-collapse]");
  const dialog = shell.querySelector("[data-home-guestbook-dialog]");
  if (
    !(panel instanceof HTMLElement) ||
    !(openButton instanceof HTMLButtonElement)
  ) {
    return;
  }
  if (!collapsed && shell.dataset.boundsReady === "false") collapsed = true;
  const activeElement = document.activeElement;
  const shouldMoveFocusToOpen = collapsed && (
    panel.contains(activeElement) ||
    (dialog instanceof HTMLElement && dialog.contains(activeElement))
  );
  const shouldMoveFocusIntoPanel = !collapsed && activeElement === openButton;
  shell.dataset.collapsed = String(collapsed);
  panel.setAttribute("aria-hidden", String(collapsed));
  panel.inert = collapsed;
  openButton.setAttribute("aria-expanded", String(!collapsed));
  openButton.setAttribute("aria-hidden", String(!collapsed));
  openButton.inert = !collapsed;
  openButton.tabIndex = collapsed ? 0 : -1;
  if (collapseButton instanceof HTMLButtonElement) {
    collapseButton.setAttribute("aria-expanded", String(!collapsed));
  }
  if (collapsed && dialog instanceof HTMLDialogElement && dialog.open) {
    dialog.close("scroll");
  }
  if (shouldMoveFocusToOpen) openButton.focus({ preventScroll: true });
  else if (shouldMoveFocusIntoPanel && collapseButton instanceof HTMLButtonElement) {
    collapseButton.focus({ preventScroll: true });
  }
}

function bindDialog(shell) {
  const dialog = shell.querySelector("[data-home-guestbook-dialog]");
  const openButton = shell.querySelector("[data-home-guestbook-open-dialog]");
  if (!(dialog instanceof HTMLDialogElement)) return;
  const open = () => {
    if (!dialog.open) dialog.showModal();
    dialog.querySelector("textarea")?.focus({ preventScroll: true });
  };
  openButton?.addEventListener("click", open);
  shell.querySelectorAll("[data-home-guestbook-close-dialog]").forEach((button) => {
    button.addEventListener("click", () => dialog.close("cancel"));
  });
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close("cancel");
  });
  const field = dialog.querySelector("textarea");
  const counter = dialog.querySelector("[data-guestbook-count]");
  if (field instanceof HTMLTextAreaElement && counter instanceof HTMLElement) {
    const update = () => {
      counter.textContent = `${field.value.length} / ${field.maxLength || 100}`;
    };
    field.addEventListener("input", update);
    update();
  }
  if (shell.dataset.dialogOpen === "true") {
    if (dialog.open) dialog.close();
    open();
  }
}

function bindGlobalGuestbookEvents() {
  if (globalGuestbookEventsBound) return;
  globalGuestbookEventsBound = true;
  window.addEventListener("resize", scheduleGuestbookBounds, { passive: true });
  window.addEventListener("scroll", scheduleGuestbookBounds, { passive: true });
  document.addEventListener("htmx:beforeRequest", (event) => {
    const trigger = event.detail?.elt;
    if (!(trigger instanceof HTMLElement)) return;
    const form = trigger.matches("[data-home-guestbook-form]")
      ? trigger
      : trigger.closest("[data-home-guestbook-form]");
    const shell = form?.closest("[data-home-guestbook-shell]");
    if (
      shell instanceof HTMLElement &&
      form instanceof HTMLFormElement
    ) {
      pendingGuestbookState = {
        collapsed: shell.dataset.collapsed === "true",
        manuallyCollapsed: shell.dataset.manuallyCollapsed === "true",
      };
    }
    if (trigger.matches("[data-guestbook-load-more]")) {
      trigger.remove();
    }
  });
  document.addEventListener("htmx:afterSwap", (event) => {
    const shell = guestbookShellFromSwap(event);
    if (!(shell instanceof HTMLElement)) return;
    initializeHomeGuestbook(shell);
    if (pendingGuestbookState !== null) {
      const state = pendingGuestbookState;
      shell.dataset.manuallyCollapsed = String(state.manuallyCollapsed);
      if (shell.dataset.boundsReady !== "true") {
        syncGuestbookBounds(shell);
      }
      setCollapsed(shell, state.collapsed);
      pendingGuestbookState = null;
    }
  });
}

function bindShell(shell) {
  if (!(shell instanceof HTMLElement) || boundGuestbookShells.has(shell)) return;
  boundGuestbookShells.add(shell);
  bindDialog(shell);
  const page = shell.closest("[data-home-page]");
  const header = document.querySelector("[data-site-header]");
  const heroContent = page?.querySelector(".home-hero__content");
  if ("ResizeObserver" in window && header instanceof HTMLElement && heroContent) {
    guestbookBoundsObserver?.disconnect();
    guestbookBoundsObserver = new ResizeObserver(scheduleGuestbookBounds);
    guestbookBoundsObserver.observe(header);
    guestbookBoundsObserver.observe(heroContent);
  }
  syncGuestbookBounds(shell);
  const openButton = shell.querySelector("[data-home-guestbook-open]");
  openButton?.addEventListener("click", () => {
    const page = shell.closest("[data-home-page]");
    if (shell.dataset.boundsReady !== "true") {
      shell.dataset.manuallyCollapsed = "false";
      const hero = page?.querySelector(".home-hero");
      const header = document.querySelector("[data-site-header]");
      if (hero instanceof HTMLElement) {
        const headerHeight =
          header instanceof HTMLElement ? header.getBoundingClientRect().height : 0;
        const top = Math.max(
          0,
          hero.getBoundingClientRect().top + window.scrollY - headerHeight,
        );
        const reduceMotion = window.matchMedia(
          "(prefers-reduced-motion: reduce)",
        ).matches;
        window.scrollTo({ top, behavior: reduceMotion ? "auto" : "smooth" });
      }
      return;
    }
    shell.dataset.manuallyCollapsed = "false";
    setCollapsed(shell, false);
  });
  const collapseButton = shell.querySelector("[data-home-guestbook-collapse]");
  collapseButton?.addEventListener("click", () => {
    shell.dataset.manuallyCollapsed = "true";
    setCollapsed(shell, true);
  });
  const articles = page?.querySelector("[data-home-articles]");
  if (!(articles instanceof HTMLElement) || !("IntersectionObserver" in window)) {
    setCollapsed(shell, shell.dataset.collapsed === "true");
    return;
  }
  let articlesVisible = false;
  const observer = new IntersectionObserver(
    (entries) => {
      const entry = entries[0];
      if (!entry) return;
      articlesVisible = entry.isIntersecting;
      shell.dataset.articlesVisible = String(articlesVisible);
      if (articlesVisible) setCollapsed(shell, true);
      else if (shell.dataset.manuallyCollapsed !== "true") setCollapsed(shell, false);
    },
    { rootMargin: "0px 0px -1px" },
  );
  observer.observe(articles);
  shell.dataset.articlesVisible = "false";
  setCollapsed(shell, false);
}

export function initializeHomeGuestbook(root = document) {
  bindGlobalGuestbookEvents();
  if (root instanceof HTMLElement && root.matches("[data-home-guestbook-shell]")) {
    bindShell(root);
  }
  root.querySelectorAll?.("[data-home-guestbook-shell]").forEach(bindShell);
}
