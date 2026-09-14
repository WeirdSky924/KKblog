import { initializeOpportunityFilterPickers } from "./opportunity-filter-picker.js";

let filtersOpen = false;
let pendingPosition = null;
const filterTimers = new WeakMap();
const DEFAULT_JOB_COLUMNS = Object.freeze([
  "company",
  "title",
  "recruitment",
  "city",
  "published",
  "actions",
]);
const JOB_COLUMN_KEYS = new Set([
  "company",
  "title",
  "recruitment",
  "cohort",
  "category",
  "city",
  "verification",
  "published",
  "actions",
]);
const JOB_COLUMNS_STORAGE_KEY = "kaj.opportunities.visible-job-columns.v1";

function loadVisibleJobColumns() {
  try {
    const value = JSON.parse(
      window.localStorage.getItem(JOB_COLUMNS_STORAGE_KEY) || "null",
    );
    if (!Array.isArray(value) || value.some((column) => !JOB_COLUMN_KEYS.has(column))) {
      return new Set(DEFAULT_JOB_COLUMNS);
    }
    return new Set(value);
  } catch {
    return new Set(DEFAULT_JOB_COLUMNS);
  }
}

function storeVisibleJobColumns(columns) {
  try {
    window.localStorage.setItem(
      JOB_COLUMNS_STORAGE_KEY,
      JSON.stringify([...columns].filter((column) => JOB_COLUMN_KEYS.has(column))),
    );
  } catch {
    // Private browsing and strict storage policies should not block the table.
  }
}

let visibleJobColumns = loadVisibleJobColumns();

function submitOpportunityFilter(form) {
  if (!(form instanceof HTMLFormElement)) return;
  if (typeof form.requestSubmit === "function") {
    form.requestSubmit();
    return;
  }
  form.dispatchEvent(
    new CustomEvent("opportunity-filter-change", { bubbles: true }),
  );
}

function bindDisclosure(root) {
  const disclosure = root.querySelector?.("[data-opportunity-filter-disclosure]");
  if (!(disclosure instanceof HTMLDetailsElement)) {
    return;
  }
  if (!disclosure.hasAttribute("open")) {
    disclosure.open = filtersOpen;
  } else {
    filtersOpen = true;
  }
  if (disclosure.dataset.opportunityBound === "true") {
    return;
  }
  disclosure.dataset.opportunityBound = "true";
  disclosure.addEventListener("toggle", () => {
    filtersOpen = disclosure.open;
  });
}

function bindFilterChanges(root) {
  const form = root.querySelector?.("[data-opportunity-filter-form]");
  if (!(form instanceof HTMLFormElement) || form.dataset.opportunityBound === "true") {
    return;
  }
  form.dataset.opportunityBound = "true";
  form.addEventListener("change", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLInputElement) || target.type !== "checkbox") {
      return;
    }
    if (target.closest("[data-opportunity-filter-picker]")) {
      return;
    }
    const existing = filterTimers.get(form);
    if (existing) {
      window.clearTimeout(existing);
    }
    filterTimers.set(
      form,
      window.setTimeout(() => {
        filterTimers.delete(form);
        submitOpportunityFilter(form);
      }, 120),
    );
  });
}

function bindJobColumns(root) {
  const table = root.querySelector?.("[data-opportunity-job-table]");
  const picker = root.querySelector?.("[data-opportunity-column-picker]");
  if (
    !(table instanceof HTMLTableElement) ||
    !(picker instanceof HTMLDetailsElement) ||
    picker.dataset.opportunityColumnsBound === "true"
  ) {
    return;
  }
  const toggles = Array.from(
    picker.querySelectorAll("[data-opportunity-column-toggle]"),
  ).filter((toggle) => toggle instanceof HTMLButtonElement);
  if (!toggles.length) return;
  picker.dataset.opportunityColumnsBound = "true";

  const apply = () => {
    const next = new Set(
      toggles
        .filter((toggle) => toggle.getAttribute("aria-checked") === "true")
        .map((toggle) => toggle.value),
    );
    // Operations remain reachable even if a user hides every data column.
    next.add("actions");
    visibleJobColumns = next;
    toggles.forEach((toggle) => {
      const selected = toggle.disabled || visibleJobColumns.has(toggle.value);
      toggle.setAttribute("aria-checked", String(selected));
      toggle.classList.toggle("is-selected", selected);
    });
    table.querySelectorAll("[data-opportunity-column]").forEach((cell) => {
      if (!(cell instanceof HTMLElement)) return;
      cell.hidden = !visibleJobColumns.has(cell.dataset.opportunityColumn || "");
    });
  };

  toggles.forEach((toggle) => {
    toggle.setAttribute(
      "aria-checked",
      String(toggle.disabled || visibleJobColumns.has(toggle.value)),
    );
    toggle.addEventListener("click", () => {
      if (toggle.disabled) return;
      toggle.setAttribute(
        "aria-checked",
        String(toggle.getAttribute("aria-checked") !== "true"),
      );
      apply();
      storeVisibleJobColumns(visibleJobColumns);
    });
  });
  apply();
}

function focusIdentity(element) {
  if (!(element instanceof HTMLElement)) {
    return null;
  }
  if (element.id) {
    return { id: element.id };
  }
  if (element instanceof HTMLInputElement && element.name) {
    return { name: element.name, value: element.value };
  }
  return null;
}

function restorePosition() {
  if (!pendingPosition) {
    return;
  }
  const { x, y, focus } = pendingPosition;
  pendingPosition = null;
  window.scrollTo({ left: x, top: y, behavior: "instant" });
  let target = focus?.id ? document.getElementById(focus.id) : null;
  if (!target && focus?.name) {
    target = Array.from(document.querySelectorAll(`[name="${CSS.escape(focus.name)}"]`)).find(
      (candidate) =>
        !(candidate instanceof HTMLInputElement) || candidate.value === focus.value,
    );
  }
  if (target instanceof HTMLElement) {
    target.focus({ preventScroll: true });
  }
}

function bindRequestPositionSupport() {
  if (document.documentElement.dataset.opportunitiesBound === "true") {
    return;
  }
  document.documentElement.dataset.opportunitiesBound = "true";
  document.addEventListener("htmx:beforeRequest", (event) => {
    const trigger = event.detail?.elt;
    if (!(trigger instanceof Element) || !trigger.closest("[data-opportunity-workspace]")) {
      return;
    }
    pendingPosition = {
      x: window.scrollX,
      y: window.scrollY,
      focus: focusIdentity(document.activeElement),
    };
  });
  document.addEventListener("htmx:afterSettle", (event) => {
    if (event.detail?.target?.matches?.("[data-opportunity-workspace]")) {
      requestAnimationFrame(restorePosition);
    }
  });
  document.addEventListener("htmx:afterRequest", (event) => {
    if (
      event.detail?.requestConfig?.parameters?.selected !== "false" ||
      event.detail?.successful !== true ||
      !event.detail?.requestConfig?.parameters?.opportunity_id
    ) {
      return;
    }
    const bookmarkFilter = document.querySelector(
      "[data-opportunity-filter-form] input[name='bookmarked']:checked",
    );
    const workspace = document.querySelector("[data-opportunity-workspace]");
    const isBookmarksView =
      workspace instanceof HTMLElement && workspace.dataset.opportunityView === "bookmarks";
    if (bookmarkFilter instanceof HTMLInputElement || isBookmarksView) {
      submitOpportunityFilter(
        document.querySelector("[data-opportunity-filter-form]"),
      );
    }
  });
  for (const eventName of ["htmx:sendError", "htmx:responseError", "htmx:timeout"]) {
    document.addEventListener(eventName, () => {
      pendingPosition = null;
    });
  }
}

export function initializeOpportunities(root = document) {
  initializeOpportunityFilterPickers(root);
  const workspace =
    root instanceof HTMLElement && root.matches("[data-opportunity-workspace]")
      ? root
      : root.querySelector?.("[data-opportunity-workspace]");
  if (!(workspace instanceof HTMLElement)) {
    return;
  }
  bindRequestPositionSupport();
  bindDisclosure(workspace);
  bindFilterChanges(workspace);
  bindJobColumns(workspace);
}
