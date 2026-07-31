import htmx from "htmx.org";

let pendingSubmission = null;
let supportBound = false;

function liveForms(root) {
  const forms = [];
  if (root instanceof HTMLFormElement && root.hasAttribute("data-live-submit")) {
    forms.push(root);
  }
  root.querySelectorAll?.("form[data-live-submit]").forEach((form) => {
    forms.push(form);
  });
  return forms;
}

function processEnhancedForm(form) {
  if (document.readyState === "loading") {
    return;
  }
  htmx.process(form);
}

export function initializeLiveSubmitForms(root = document) {
  liveForms(root).forEach((form) => {
    if (!(form instanceof HTMLFormElement) || form.dataset.liveBound === "true") {
      return;
    }
    form.dataset.liveBound = "true";
    form.setAttribute("hx-boost", "true");
    form.setAttribute("hx-target", "#main-content");
    form.setAttribute("hx-select", "#main-content");
    form.setAttribute("hx-swap", "outerHTML show:none focus-scroll:false");
    form.setAttribute("hx-sync", "#main-content:replace");
    processEnhancedForm(form);
  });
}

function liveFormFromEvent(event) {
  const trigger = event.detail?.elt;
  if (!(trigger instanceof Element)) {
    return null;
  }
  const form = trigger.closest("form[data-live-submit]");
  return form instanceof HTMLFormElement ? form : null;
}

function formControls(form) {
  return Array.from(form.querySelectorAll("button, input, select, textarea"));
}

function captureSubmissionPosition(event) {
  const form = liveFormFromEvent(event);
  if (!form) {
    return;
  }
  const controls = formControls(form);
  const active = form.contains(document.activeElement) ? document.activeElement : null;
  const anchor = active instanceof HTMLElement ? active : form;
  pendingSubmission = {
    key: form.dataset.liveSubmit || "",
    controlIndex: controls.indexOf(anchor),
    top: anchor.getBoundingClientRect().top,
    xhr: event.detail?.xhr,
    status: 200,
  };
}

function recordSubmissionStatus(event) {
  if (pendingSubmission?.xhr === event.detail?.xhr) {
    pendingSubmission.status = event.detail?.xhr?.status ?? 200;
  }
}

function restoreSubmissionPosition(event) {
  const state = pendingSubmission;
  if (!state || state.xhr !== event.detail?.xhr) {
    return;
  }
  pendingSubmission = null;
  const form = Array.from(document.querySelectorAll("form[data-live-submit]")).find(
    (candidate) => candidate.dataset.liveSubmit === state.key,
  );
  if (!(form instanceof HTMLFormElement)) {
    return;
  }
  const controls = formControls(form);
  const anchor = controls[state.controlIndex] ?? form;
  window.requestAnimationFrame(() => {
    window.scrollBy(0, anchor.getBoundingClientRect().top - state.top);
    if (state.status < 400 && anchor instanceof HTMLElement) {
      anchor.focus({ preventScroll: true });
    }
  });
}

function clearPendingSubmission(event) {
  if (pendingSubmission?.xhr === event.detail?.xhr) {
    pendingSubmission = null;
  }
}

export function initializeLiveSubmitSupport() {
  if (supportBound) {
    return;
  }
  supportBound = true;
  document.addEventListener("htmx:beforeRequest", captureSubmissionPosition);
  document.addEventListener("htmx:beforeSwap", recordSubmissionStatus);
  document.addEventListener("htmx:afterSettle", restoreSubmissionPosition);
  document.addEventListener("htmx:sendError", clearPendingSubmission);
  document.addEventListener("htmx:responseError", clearPendingSubmission);
  document.addEventListener("htmx:timeout", clearPendingSubmission);
}
