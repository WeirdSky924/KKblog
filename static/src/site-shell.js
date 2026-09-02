const DISCLOSURE_CLOSE_DELAY = 220;
const disclosureCloseTimers = new WeakMap();
let siteHeaderResizeObserver = null;
let observedSiteHeader = null;

function applySiteHeaderHeight(header) {
  const height = header.getBoundingClientRect().height;
  if (height > 0) {
    document.documentElement.style.setProperty(
      "--site-header-height",
      `${height}px`,
    );
  }
}

export function initializeSiteHeaderMetrics(root = document) {
  const header =
    root instanceof HTMLElement && root.matches("[data-site-header]")
      ? root
      : root.querySelector?.("[data-site-header]");
  if (!(header instanceof HTMLElement)) {
    return;
  }

  applySiteHeaderHeight(header);
  if (observedSiteHeader === header) {
    return;
  }

  siteHeaderResizeObserver?.disconnect();
  observedSiteHeader = header;
  if ("ResizeObserver" in window) {
    siteHeaderResizeObserver = new ResizeObserver(() => {
      applySiteHeaderHeight(header);
    });
    siteHeaderResizeObserver.observe(header);
  }
}

function cancelDisclosureClose(disclosure) {
  const timer = disclosureCloseTimers.get(disclosure);
  if (timer !== undefined) {
    window.clearTimeout(timer);
    disclosureCloseTimers.delete(disclosure);
  }
}

function disclosureShouldRemainOpen(disclosure) {
  return (
    disclosure.matches(":hover") ||
    disclosure.contains(document.activeElement)
  );
}

function scheduleDisclosureClose(disclosure) {
  cancelDisclosureClose(disclosure);
  const timer = window.setTimeout(() => {
    disclosureCloseTimers.delete(disclosure);
    if (!disclosureShouldRemainOpen(disclosure)) {
      disclosure.open = false;
    }
  }, DISCLOSURE_CLOSE_DELAY);
  disclosureCloseTimers.set(disclosure, timer);
}

function bindHoverDisclosure(disclosure) {
  disclosure.addEventListener("pointerenter", () => {
    cancelDisclosureClose(disclosure);
    disclosure.open = true;
  });
  disclosure.addEventListener("pointerleave", () => {
    scheduleDisclosureClose(disclosure);
  });
  disclosure.addEventListener("focusin", () => {
    cancelDisclosureClose(disclosure);
  });
}

export function initializePersonalMenus(root = document) {
  if (!window.matchMedia("(hover: hover)").matches) {
    return;
  }
  root.querySelectorAll?.("[data-personal-menu]").forEach((menu) => {
    if (!(menu instanceof HTMLDetailsElement) || menu.dataset.hoverBound === "true") {
      return;
    }
    menu.dataset.hoverBound = "true";
    bindHoverDisclosure(menu);
    menu.addEventListener("focusout", () => {
      scheduleDisclosureClose(menu);
    });
  });
}

export function initializeNotificationCenters(root = document) {
  root.querySelectorAll?.("[data-notification-center]").forEach((center) => {
    if (
      !(center instanceof HTMLDetailsElement) ||
      center.dataset.notificationBound === "true"
    ) {
      return;
    }
    center.dataset.notificationBound = "true";
    if (window.matchMedia("(hover: hover)").matches) {
      bindHoverDisclosure(center);
    }
    center.addEventListener("focusout", () => {
      scheduleDisclosureClose(center);
    });
  });
}

function isBoostedRequest(detail) {
  return detail?.boosted === true || detail?.requestConfig?.boosted === true;
}

function isCompleteDocumentResponse(responseText) {
  const normalized = responseText?.trimStart().toLowerCase() ?? "";
  return normalized.startsWith("<!doctype html") || normalized.startsWith("<html");
}

function boostedNavigationPath(detail) {
  return (
    detail?.pathInfo?.responsePath ||
    detail?.pathInfo?.finalRequestPath ||
    detail?.requestConfig?.path ||
    ""
  );
}

function syncBodyAttributes(responseText) {
  if (!responseText) {
    return;
  }
  const responseDocument = new DOMParser().parseFromString(responseText, "text/html");
  if (responseDocument.body) {
    document.body.className = responseDocument.body.className;
  }
}

function pushRedirectedFormUrl(detail) {
  const verb = detail?.requestConfig?.verb?.toLowerCase();
  const responseUrl = detail?.xhr?.responseURL;
  if (
    !isBoostedRequest(detail) ||
    verb === "get" ||
    detail?.successful !== true ||
    !responseUrl
  ) {
    return;
  }
  const next = new URL(responseUrl, window.location.href);
  const current = new URL(window.location.href);
  if (
    next.origin === current.origin &&
    `${next.pathname}${next.search}${next.hash}` !==
      `${current.pathname}${current.search}${current.hash}`
  ) {
    window.htmx?.pushUrl(`${next.pathname}${next.search}${next.hash}`);
  }
}

export function initializeBoostedPageShell() {
  if (document.documentElement.dataset.boostedShellBound === "true") {
    return;
  }
  document.documentElement.dataset.boostedShellBound = "true";
  document.addEventListener("htmx:beforeSwap", (event) => {
    if (event.detail?.target === document.body && isBoostedRequest(event.detail)) {
      if (!isCompleteDocumentResponse(event.detail?.xhr?.responseText)) {
        event.preventDefault();
        event.detail.shouldSwap = false;
        const path = boostedNavigationPath(event.detail);
        if (path && event.detail?.requestConfig?.verb?.toLowerCase() === "get") {
          window.location.assign(path);
        }
        return;
      }
      syncBodyAttributes(event.detail?.xhr?.responseText);
    }
  });
  document.addEventListener("htmx:afterRequest", (event) => {
    pushRedirectedFormUrl(event.detail);
  });
}
