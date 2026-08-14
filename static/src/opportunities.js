import { initializeOpportunityFilterPickers } from "./opportunity-filter-picker.js";

let filtersOpen = false;
let pendingPosition = null;
const filterTimers = new WeakMap();

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
        form.dispatchEvent(
          new CustomEvent("opportunity-filter-change", { bubbles: true }),
        );
      }, 120),
    );
  });
}

function bindEvidence(root) {
  root.querySelectorAll?.("[data-opportunity-evidence]").forEach((button) => {
    if (
      !(button instanceof HTMLButtonElement) ||
      button.dataset.opportunityBound === "true"
    ) {
      return;
    }
    button.dataset.opportunityBound = "true";
    button.addEventListener("click", () => {
      const targetId = button.getAttribute("aria-controls");
      const evidence = targetId ? document.getElementById(targetId) : null;
      if (!(evidence instanceof HTMLElement)) {
        return;
      }
      const expanded = button.getAttribute("aria-expanded") === "true";
      evidence.hidden = expanded;
      button.setAttribute("aria-expanded", String(!expanded));
      button.title = expanded ? "查看公开证据" : "收起公开证据";
    });
  });
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
    if (bookmarkFilter instanceof HTMLInputElement) {
      document
        .querySelector("[data-opportunity-filter-form]")
        ?.dispatchEvent(
          new CustomEvent("opportunity-filter-change", { bubbles: true }),
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
  bindEvidence(workspace);
}
