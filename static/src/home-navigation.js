const COMPACT_NAVIGATION_QUERY = "(max-width: 63.99rem)";
const SECTION_SNAP_TOLERANCE = 24;
const TOUCH_SNAP_MIN_DISTANCE = 32;
const SECTION_SNAP_DURATION = 650;

function documentTop(element) {
  return element.getBoundingClientRect().top + window.scrollY;
}

function siteHeaderHeight() {
  const header = document.querySelector("[data-site-header]");
  return header instanceof HTMLElement
    ? header.getBoundingClientRect().height
    : 0;
}

function snapTarget(element) {
  return Math.max(0, documentTop(element) - siteHeaderHeight());
}

function bindHomeSectionSnapping(page) {
  if (!(page instanceof HTMLElement) || page.dataset.sectionSnapBound === "true") {
    return;
  }
  const hero = page.querySelector(".home-hero");
  const articles = page.querySelector("[data-home-articles]");
  if (!(hero instanceof HTMLElement) || !(articles instanceof HTMLElement)) {
    return;
  }

  page.dataset.sectionSnapBound = "true";
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

  const insideNavigation = (target) =>
    target instanceof Element &&
    target.closest("[data-home-navigation-panel]") !== null;

  page.addEventListener(
    "wheel",
    (event) => {
      if (event.ctrlKey || event.deltaY === 0 || insideNavigation(event.target)) {
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

function bindNavigationShell(shell) {
  if (!(shell instanceof HTMLElement) || shell.dataset.bound === "true") {
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

  shell.dataset.bound = "true";
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
