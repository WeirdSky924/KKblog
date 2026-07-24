const COMMENT_SORT_STORAGE_KEY = "kaj.comment-sort";
const COMMENT_SORT_VALUES = new Set(["earliest", "latest", "hottest"]);

export function initializeCommentForms(root = document) {
  root.querySelectorAll?.("[data-comment-form]").forEach((form) => {
    if (!(form instanceof HTMLFormElement) || form.dataset.countBound === "true") {
      return;
    }
    const body = form.querySelector("textarea[name='body']");
    const count = form.querySelector("[data-comment-count]");
    if (!(body instanceof HTMLTextAreaElement) || !(count instanceof HTMLElement)) {
      return;
    }
    form.dataset.countBound = "true";
    const update = () => {
      count.textContent = `${Array.from(body.value).length} / 100`;
    };
    body.addEventListener("input", update);
    update();
  });
}

function readCommentSort() {
  try {
    const value = window.localStorage.getItem(COMMENT_SORT_STORAGE_KEY);
    return COMMENT_SORT_VALUES.has(value) ? value : null;
  } catch {
    return null;
  }
}

function storeCommentSort(value) {
  if (!COMMENT_SORT_VALUES.has(value)) {
    return;
  }
  try {
    window.localStorage.setItem(COMMENT_SORT_STORAGE_KEY, value);
  } catch {
    // Browser storage is optional; server ordering remains fully functional.
  }
}

function updateCommentSortControls(thread, value) {
  if (!COMMENT_SORT_VALUES.has(value)) {
    return;
  }
  thread.dataset.sort = value;
  thread.querySelectorAll("[data-comment-sort-control]").forEach((control) => {
    control.setAttribute(
      "aria-pressed",
      String(control.getAttribute("data-comment-sort-control") === value),
    );
  });
}

export function initializeCommentThreads(root = document) {
  const threads = new Set();
  if (root instanceof Element) {
    if (root.matches("[data-comment-thread]")) {
      threads.add(root);
    }
    const parent = root.closest("[data-comment-thread]");
    if (parent) {
      threads.add(parent);
    }
  }
  root.querySelectorAll?.("[data-comment-thread]").forEach((thread) => {
    threads.add(thread);
  });
  threads.forEach((thread) => {
    const list = thread.querySelector("[data-comment-public-list]");
    const current = list?.getAttribute("data-sort") || thread.dataset.sort;
    if (COMMENT_SORT_VALUES.has(current)) {
      updateCommentSortControls(thread, current);
    }
    if (thread.dataset.sortBound !== "true") {
      thread.dataset.sortBound = "true";
      thread.querySelectorAll("[data-comment-sort-control]").forEach((control) => {
        control.addEventListener("click", () => {
          const value = control.getAttribute("data-comment-sort-control");
          updateCommentSortControls(thread, value);
          storeCommentSort(value);
        });
      });
    }
    if (thread.dataset.sortRestored !== "true") {
      thread.dataset.sortRestored = "true";
      const preferred = readCommentSort();
      if (preferred && preferred !== current) {
        thread
          .querySelector(`[data-comment-sort-control="${preferred}"]`)
          ?.click();
      }
    }
  });
}

export function focusLoadedCommentReply(root = document) {
  const item =
    root.querySelector?.("[data-comment-reply-focus]") ||
    document.querySelector("[data-comment-reply-focus]");
  if (!(item instanceof HTMLElement)) {
    return;
  }
  requestAnimationFrame(() => {
    item.focus({ preventScroll: true });
    delete item.dataset.commentReplyFocus;
  });
}
