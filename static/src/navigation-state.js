const NAVIGATION_INTENT_KEY = "kaj.navigation-intent";
const NAVIGATION_INTENT_MAX_AGE = 15_000;

function readIntent() {
  try {
    const raw = window.sessionStorage.getItem(NAVIGATION_INTENT_KEY);
    window.sessionStorage.removeItem(NAVIGATION_INTENT_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function writeIntent(intent) {
  try {
    window.sessionStorage.setItem(NAVIGATION_INTENT_KEY, JSON.stringify(intent));
  } catch {
    // Navigation still works when session storage is unavailable.
  }
}

function resetNavigationScroll() {
  const previousRestoration = window.history.scrollRestoration;
  const root = document.documentElement;
  const previousOverflowAnchor = root.style.overflowAnchor;
  window.history.scrollRestoration = "manual";
  root.style.overflowAnchor = "none";
  const reset = () => window.scrollTo(0, 0);
  const finish = () => {
    // Some engines restore the previous scroll offset after pageshow and the first paint.
    reset();
    window.requestAnimationFrame(() => {
      reset();
      window.requestAnimationFrame(() => {
        reset();
        window.setTimeout(() => {
          reset();
          root.style.overflowAnchor = previousOverflowAnchor;
          window.history.scrollRestoration = previousRestoration;
        }, 0);
      });
    });
  };

  reset();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", reset, { once: true });
  }
  window.addEventListener("load", reset, { once: true });
  window.addEventListener(
    "pageshow",
    finish,
    { once: true },
  );
}

const intent = readIntent();
if (
  intent?.kind === "top" &&
  Number.isFinite(intent.createdAt) &&
  Date.now() - intent.createdAt <= NAVIGATION_INTENT_MAX_AGE
) {
  resetNavigationScroll();
}

document.addEventListener(
  "click",
  (event) => {
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey ||
      !(event.target instanceof Element)
    ) {
      return;
    }
    const link = event.target.closest("a[href]");
    if (
      !(link instanceof HTMLAnchorElement) ||
      link.hasAttribute("download") ||
      link.target === "_blank" ||
      link.hasAttribute("data-preserve-scroll") ||
      link.hasAttribute("hx-get") ||
      link.closest('[hx-boost="true"]')
    ) {
      return;
    }
    const destination = new URL(link.href, window.location.href);
    if (destination.origin !== window.location.origin || destination.hash) {
      return;
    }
    writeIntent({ kind: "top", createdAt: Date.now() });
  },
  true,
);
