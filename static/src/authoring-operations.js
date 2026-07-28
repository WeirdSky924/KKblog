let countdownTimer = null;

function countdownText(milliseconds) {
  if (milliseconds <= 0) {
    return "即将公开";
  }
  const seconds = Math.ceil(milliseconds / 1000);
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainder = seconds % 60;
  if (hours > 0) {
    return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
  }
  return `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
}

function updateCountdowns() {
  const now = Date.now();
  document.querySelectorAll("[data-buffer-countdown]").forEach((node) => {
    if (!(node instanceof HTMLTimeElement)) {
      return;
    }
    const visibleAt = Date.parse(node.dataset.visibleAt || "");
    if (!Number.isFinite(visibleAt)) {
      node.textContent = "时间不可用";
      node.dataset.expired = "true";
      return;
    }
    const remaining = visibleAt - now;
    node.textContent = countdownText(remaining);
    node.toggleAttribute("data-expired", remaining <= 0);
    node.setAttribute(
      "aria-label",
      remaining <= 0 ? "即将公开" : `距离公开还有 ${node.textContent}`,
    );
  });
}

function initializeDecisionForms(root) {
  root.querySelectorAll?.("[data-import-decision-form]").forEach((form) => {
    if (!(form instanceof HTMLFormElement) || form.dataset.bound === "true") {
      return;
    }
    const included = form.elements.namedItem("included");
    const decision = form.elements.namedItem("decision");
    if (!(included instanceof HTMLInputElement) || !(decision instanceof HTMLSelectElement)) {
      return;
    }
    form.dataset.bound = "true";
    const update = () => {
      if (!included.checked) {
        if (decision.value !== "SKIP") {
          decision.dataset.previousValue = decision.value;
        }
        decision.value = "SKIP";
        return;
      }
      if (decision.value === "SKIP" && decision.dataset.previousValue) {
        decision.value = decision.dataset.previousValue;
      }
    };
    included.addEventListener("change", update);
    decision.addEventListener("change", () => {
      if (decision.value !== "SKIP") {
        decision.dataset.previousValue = decision.value;
      }
    });
    update();
  });
}

export function initializeAuthorOperations(root = document) {
  initializeDecisionForms(root);
  updateCountdowns();
  if (countdownTimer === null && document.querySelector("[data-buffer-countdown]")) {
    countdownTimer = window.setInterval(updateCountdowns, 1000);
  }
}
