const COMPACT_NAVIGATION_QUERY = "(max-width: 63.99rem)";
const SECTION_SNAP_TOLERANCE = 24;
const TOUCH_SNAP_MIN_DISTANCE = 32;
const SECTION_SNAP_DURATION = 650;
const NAVIGATION_PAGING_TOLERANCE = 2;
const boundHomePages = new WeakSet();
const boundNavigationShells = new WeakSet();
const boundNavigationBranches = new WeakSet();
const boundNavigationScrollers = new WeakSet();

export function getNavigationPagingState(
  { clientHeight, scrollHeight, scrollTop },
  tolerance = NAVIGATION_PAGING_TOLERANCE,
) {
  const boundaryTolerance = Math.max(0, tolerance);
  return {
    canPageDown:
      scrollTop + clientHeight < scrollHeight - boundaryTolerance,
    canPageUp: scrollTop > boundaryTolerance,
  };
}

export function findNavigationPageTarget(
  items,
  { direction, maxScroll, viewportEnd, viewportStart },
  tolerance = NAVIGATION_PAGING_TOLERANCE,
) {
  const boundaryTolerance = Math.max(0, tolerance);
  const viewportHeight = viewportEnd - viewportStart;
  if (
    !Array.isArray(items) ||
    items.length === 0 ||
    viewportHeight <= 0 ||
    (direction !== "up" && direction !== "down")
  ) {
    return null;
  }

  let candidate;
  if (direction === "down") {
    candidate = items.find(
      (item) => item.bottom > viewportEnd + boundaryTolerance,
    );
  } else {
    candidate = items.findLast(
      (item) => item.top < viewportStart - boundaryTolerance,
    );
  }
  if (!candidate) {
    return null;
  }

  let target;
  if (direction === "down") {
    target =
      candidate.top > viewportStart + boundaryTolerance
        ? candidate.top
        : candidate.bottom - viewportHeight;
  } else {
    target =
      candidate.bottom < viewportEnd - boundaryTolerance
        ? candidate.bottom - viewportHeight
        : candidate.top;
  }
  const clampedTarget = Math.min(Math.max(0, target), Math.max(0, maxScroll));
  return Math.abs(clampedTarget - viewportStart) <= boundaryTolerance
    ? null
    : clampedTarget;
}

function applyBranchState(toggle, expanded) {
  const controls = toggle.getAttribute("aria-controls");
  const children = controls
    ? toggle.ownerDocument.getElementById(controls)
    : null;
  if (!(children instanceof HTMLUListElement)) {
    return false;
  }
  const label = toggle.dataset.navigationBranchLabel ?? "导航";
  toggle.setAttribute("aria-expanded", String(expanded));
  toggle.title = `${expanded ? "收起" : "展开"}子项`;
  if (toggle.classList.contains("public-navigation__branch-toggle")) {
    toggle.setAttribute(
      "aria-label",
      `${expanded ? "收起" : "展开"}${label}的子项`,
    );
  }
  children.hidden = !expanded;
  return true;
}

function bindNavigationBranch(toggle) {
  if (
    !(toggle instanceof HTMLButtonElement) ||
    boundNavigationBranches.has(toggle)
  ) {
    return;
  }
  if (!applyBranchState(toggle, toggle.getAttribute("aria-expanded") === "true")) {
    return;
  }
  boundNavigationBranches.add(toggle);
  toggle.addEventListener("click", () => {
    if (
      applyBranchState(toggle, toggle.getAttribute("aria-expanded") !== "true")
    ) {
      toggle.dispatchEvent(
        new CustomEvent("navigation:layoutchange", { bubbles: true }),
      );
    }
  });
}

function initializeNavigationBranches(root = document) {
  if (
    root instanceof HTMLButtonElement &&
    root.matches("[data-navigation-branch-toggle]")
  ) {
    bindNavigationBranch(root);
  }
  root.querySelectorAll?.("[data-navigation-branch-toggle]").forEach((toggle) => {
    bindNavigationBranch(toggle);
  });
}

function documentTop(element) {
  return element.getBoundingClientRect().top + window.scrollY;
}

function siteHeaderHeight() {
  const header = document.querySelector("[data-site-header]");
  return header instanceof HTMLElement
    ? header.getBoundingClientRect().height
    : 0;
}

function bindNavigationViewportMetrics(shell) {
  const footer = document.querySelector("[data-site-footer]");
  const syncFooterHeight = () => {
    const height =
      footer instanceof HTMLElement
        ? Math.ceil(footer.getBoundingClientRect().height)
        : 0;
    shell.style.setProperty("--site-footer-height", `${Math.max(0, height)}px`);
    shell.style.setProperty(
      "--home-navigation-bottom-offset",
      `calc(${Math.max(0, height)}px + 1rem)`,
    );
  };

  syncFooterHeight();
  window.addEventListener("resize", syncFooterHeight, { passive: true });
  if (footer instanceof HTMLElement && "ResizeObserver" in window) {
    const observer = new ResizeObserver(syncFooterHeight);
    observer.observe(footer);
  }
}

function snapTarget(element) {
  return Math.max(0, documentTop(element) - siteHeaderHeight());
}

function bindHomeSectionSnapping(page) {
  if (!(page instanceof HTMLElement) || boundHomePages.has(page)) {
    return;
  }
  const hero = page.querySelector(".home-hero");
  const articles = page.querySelector("[data-home-articles]");
  if (!(hero instanceof HTMLElement) || !(articles instanceof HTMLElement)) {
    return;
  }

  boundHomePages.add(page);
  let snapping = false;
  let releaseTimer;
  let touchStart = null;

  const snapTo = (section) => {
    const reduceMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    snapping = true;
    window.scrollTo({
      behavior: reduceMotion ? "auto" : "smooth",
      top: snapTarget(section),
    });
    window.clearTimeout(releaseTimer);
    releaseTimer = window.setTimeout(() => {
      snapping = false;
    }, reduceMotion ? 0 : SECTION_SNAP_DURATION);
  };

  page.addEventListener("htmx:afterRequest", (event) => {
    const link = event.detail?.elt?.closest?.(
      "[data-home-section-link], [data-home-latest-link]",
    );
    if (
      !event.detail?.successful ||
      !(link instanceof HTMLAnchorElement) ||
      !page.contains(link) ||
      !link.closest("[data-home-navigation-panel]")
    ) {
      return;
    }
    snapTo(articles);
  });

  const insideNavigation = (target) =>
    target instanceof Element &&
    target.closest("[data-home-navigation-panel]") !== null;
  const insideGuestbook = (target) =>
    target instanceof Element &&
    target.closest("[data-home-guestbook-panel]") !== null;

  page.addEventListener(
    "wheel",
    (event) => {
      if (
        event.ctrlKey ||
        event.deltaY === 0 ||
        insideNavigation(event.target) ||
        insideGuestbook(event.target)
      ) {
        return;
      }
      if (snapping) {
        event.preventDefault();
        return;
      }

      const current = window.scrollY;
      const heroTop = snapTarget(hero);
      const articlesTop = snapTarget(articles);
      if (event.deltaY > 0 && current < articlesTop - SECTION_SNAP_TOLERANCE) {
        event.preventDefault();
        snapTo(articles);
      } else if (
        event.deltaY < 0 &&
        current > heroTop + SECTION_SNAP_TOLERANCE &&
        current <= articlesTop + SECTION_SNAP_TOLERANCE
      ) {
        event.preventDefault();
        snapTo(hero);
      }
    },
    { passive: false },
  );

  page.addEventListener(
    "touchstart",
    (event) => {
      if (event.touches.length !== 1 || insideNavigation(event.target)) {
        touchStart = null;
        return;
      }
      touchStart = {
        clientY: event.touches[0].clientY,
        scrollY: window.scrollY,
      };
    },
    { passive: true },
  );

  page.addEventListener(
    "touchend",
    (event) => {
      if (!touchStart || snapping || event.changedTouches.length !== 1) {
        touchStart = null;
        return;
      }
      const distance = touchStart.clientY - event.changedTouches[0].clientY;
      const heroTop = snapTarget(hero);
      const articlesTop = snapTarget(articles);
      if (
        distance >= TOUCH_SNAP_MIN_DISTANCE &&
        touchStart.scrollY < articlesTop - SECTION_SNAP_TOLERANCE
      ) {
        snapTo(articles);
      } else if (
        distance <= -TOUCH_SNAP_MIN_DISTANCE &&
        touchStart.scrollY > heroTop + SECTION_SNAP_TOLERANCE &&
        touchStart.scrollY <= articlesTop + SECTION_SNAP_TOLERANCE
      ) {
        snapTo(hero);
      }
      touchStart = null;
    },
    { passive: true },
  );
}

function applyCollapsedState(shell, collapsed, { moveFocus = false } = {}) {
  const panel = shell.querySelector("[data-home-navigation-panel]");
  const closeButton = shell.querySelector("[data-home-navigation-close]");
  const openButton = shell.querySelector("[data-home-navigation-open]");
  if (
    !(panel instanceof HTMLElement) ||
    !(closeButton instanceof HTMLButtonElement) ||
    !(openButton instanceof HTMLButtonElement)
  ) {
    return;
  }

  shell.dataset.collapsed = String(collapsed);
  document.documentElement.dataset.homeNavigationCollapsed = String(collapsed);
  panel.setAttribute("aria-hidden", String(collapsed));
  panel.inert = collapsed;
  openButton.setAttribute("aria-expanded", String(!collapsed));
  openButton.setAttribute("aria-hidden", String(!collapsed));
  openButton.inert = !collapsed;
  openButton.tabIndex = collapsed ? 0 : -1;

  if (moveFocus) {
    window.requestAnimationFrame(() => {
      (collapsed ? openButton : closeButton).focus({ preventScroll: true });
    });
  }
}

function markActiveSection(shell, sectionId) {
  const latest = shell.querySelector("[data-home-latest-link]");
  if (latest instanceof HTMLAnchorElement) {
    if (sectionId) {
      latest.removeAttribute("aria-current");
    } else {
      latest.setAttribute("aria-current", "page");
    }
  }
  shell.querySelectorAll("[data-home-section-link]").forEach((link) => {
    if (!(link instanceof HTMLAnchorElement)) return;
    if (link.dataset.sectionId === sectionId) {
      link.setAttribute("aria-current", "page");
    } else {
      link.removeAttribute("aria-current");
    }
  });
}

function navigationItemGeometry(viewport) {
  const viewportRect = viewport.getBoundingClientRect();
  return Array.from(
    viewport.querySelectorAll(
      ".public-navigation__item > a, .public-navigation__item > .public-navigation__row, .public-navigation__item > .public-navigation__group-label",
    ),
  )
    .map((item) => item.getBoundingClientRect())
    .filter((rect) => rect.width > 0 && rect.height > NAVIGATION_PAGING_TOLERANCE)
    .map((rect) => ({
      bottom: rect.bottom - viewportRect.top + viewport.scrollTop,
      top: rect.top - viewportRect.top + viewport.scrollTop,
    }));
}

function bindNavigationPaging(shell) {
  const viewport = shell.querySelector("[data-home-navigation-scroll]");
  const upButton = shell.querySelector('[data-home-navigation-page="up"]');
  const downButton = shell.querySelector('[data-home-navigation-page="down"]');
  if (
    !(viewport instanceof HTMLElement) ||
    !(upButton instanceof HTMLButtonElement) ||
    !(downButton instanceof HTMLButtonElement) ||
    boundNavigationScrollers.has(viewport)
  ) {
    return;
  }

  boundNavigationScrollers.add(viewport);
  let updateFrame;
  const setButtonState = (button, enabled, focusFallback) => {
    if (!enabled && button.ownerDocument.activeElement === button) {
      focusFallback?.focus({ preventScroll: true });
    }
    button.disabled = !enabled;
    button.tabIndex = enabled ? 0 : -1;
    button.setAttribute("aria-hidden", String(!enabled));
  };
  const updateControls = () => {
    updateFrame = undefined;
    const state = getNavigationPagingState(viewport);
    setButtonState(upButton, state.canPageUp, state.canPageDown ? downButton : null);
    setButtonState(
      downButton,
      state.canPageDown,
      state.canPageUp ? upButton : null,
    );
  };
  const scheduleUpdate = () => {
    if (updateFrame !== undefined) return;
    updateFrame = window.requestAnimationFrame(updateControls);
  };
  const page = (direction, button) => {
    const target = findNavigationPageTarget(navigationItemGeometry(viewport), {
      direction,
      maxScroll: viewport.scrollHeight - viewport.clientHeight,
      viewportEnd: viewport.scrollTop + viewport.clientHeight,
      viewportStart: viewport.scrollTop,
    });
    if (target === null) {
      scheduleUpdate();
      return;
    }
    viewport.scrollTo({
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "auto"
        : "smooth",
      top: target,
    });
    button.focus({ preventScroll: true });
    scheduleUpdate();
  };

  upButton.addEventListener("click", () => page("up", upButton));
  downButton.addEventListener("click", () => page("down", downButton));
  viewport.addEventListener("scroll", scheduleUpdate, { passive: true });
  shell.addEventListener("navigation:layoutchange", scheduleUpdate);
  window.addEventListener("resize", scheduleUpdate, { passive: true });
  if ("ResizeObserver" in window) {
    const observer = new ResizeObserver(scheduleUpdate);
    observer.observe(viewport);
    const navigation = viewport.querySelector("nav");
    if (navigation instanceof HTMLElement) observer.observe(navigation);
  }
  scheduleUpdate();
}

function bindNavigationShell(shell) {
  if (!(shell instanceof HTMLElement) || boundNavigationShells.has(shell)) {
    return;
  }
  const closeButton = shell.querySelector("[data-home-navigation-close]");
  const openButton = shell.querySelector("[data-home-navigation-open]");
  if (
    !(closeButton instanceof HTMLButtonElement) ||
    !(openButton instanceof HTMLButtonElement)
  ) {
    return;
  }

  boundNavigationShells.add(shell);
  bindNavigationViewportMetrics(shell);
  bindNavigationPaging(shell);
  const page = shell.closest("[data-home-page]");
  const articles = page?.querySelector("[data-home-articles]");
  const compactQuery = window.matchMedia(COMPACT_NAVIGATION_QUERY);
  let articlesVisible = false;

  const applyAutomaticState = () => {
    applyCollapsedState(shell, compactQuery.matches || !articlesVisible);
  };

  applyCollapsedState(shell, true);

  closeButton.addEventListener("click", () => {
    applyCollapsedState(shell, true, { moveFocus: true });
  });
  openButton.addEventListener("click", () => {
    applyCollapsedState(shell, false, { moveFocus: true });
  });
  shell.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && shell.dataset.collapsed !== "true") {
      event.preventDefault();
      applyCollapsedState(shell, true, { moveFocus: true });
    }
  });
  shell.addEventListener("htmx:afterRequest", (event) => {
    const link = event.detail?.elt?.closest?.(
      "[data-home-section-link], [data-home-latest-link]",
    );
    if (
      event.detail?.successful &&
      link instanceof HTMLAnchorElement &&
      shell.contains(link)
    ) {
      markActiveSection(shell, link.dataset.sectionId ?? "");
    }
  });
  compactQuery.addEventListener("change", applyAutomaticState);

  if (articles instanceof HTMLElement && "IntersectionObserver" in window) {
    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        if (!entry) return;
        articlesVisible = entry.isIntersecting;
        applyAutomaticState();
      },
      { rootMargin: "0px 0px -1px" },
    );
    observer.observe(articles);
  }
}

export function initializeHomeNavigation(root = document) {
  initializeNavigationBranches(root);
  if (root instanceof HTMLElement && root.matches("[data-home-page]")) {
    bindHomeSectionSnapping(root);
  }
  root.querySelectorAll?.("[data-home-page]").forEach((page) => {
    bindHomeSectionSnapping(page);
  });
  if (
    root instanceof HTMLElement &&
    root.matches("[data-home-navigation-shell]")
  ) {
    bindNavigationShell(root);
  }
  root.querySelectorAll?.("[data-home-navigation-shell]").forEach((shell) => {
    bindNavigationShell(shell);
  });
}
