const REVEAL_KEYS = new Set(["Enter", " "]);

export function initializePasswordReveals(root = document) {
  root.querySelectorAll?.("[data-password-reveal]").forEach((button) => {
    if (
      !(button instanceof HTMLButtonElement) ||
      button.dataset.passwordRevealBound === "true"
    ) {
      return;
    }
    const fieldId = button.getAttribute("aria-controls");
    const field = fieldId ? document.getElementById(fieldId) : null;
    if (!(field instanceof HTMLInputElement) || field.type !== "password") {
      return;
    }

    button.dataset.passwordRevealBound = "true";
    const conceal = () => {
      field.type = "password";
      button.setAttribute("aria-pressed", "false");
    };
    const reveal = () => {
      field.type = "text";
      button.setAttribute("aria-pressed", "true");
    };

    button.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      event.preventDefault();
      button.setPointerCapture?.(event.pointerId);
      reveal();
    });
    button.addEventListener("pointerup", conceal);
    button.addEventListener("pointercancel", conceal);
    button.addEventListener("pointerleave", conceal);
    button.addEventListener("lostpointercapture", conceal);
    button.addEventListener("keydown", (event) => {
      if (!REVEAL_KEYS.has(event.key) || event.repeat) return;
      event.preventDefault();
      reveal();
    });
    button.addEventListener("keyup", (event) => {
      if (!REVEAL_KEYS.has(event.key)) return;
      event.preventDefault();
      conceal();
    });
    button.addEventListener("blur", conceal);
    field.form?.addEventListener("submit", conceal);
    window.addEventListener("blur", conceal);
  });
}
