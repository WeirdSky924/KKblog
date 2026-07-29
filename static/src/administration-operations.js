export function initializeAdministrationOperations(root = document) {
  root.querySelectorAll?.("[data-export-scope-form]").forEach((form) => {
    if (!(form instanceof HTMLFormElement) || form.dataset.scopeBound === "true") {
      return;
    }
    const scope = form.elements.namedItem("scope");
    if (!(scope instanceof HTMLSelectElement)) {
      return;
    }
    const update = () => {
      form.querySelectorAll("[data-export-scope-field]").forEach((group) => {
        const active = group.dataset.exportScopeField === scope.value;
        group.hidden = !active;
        group.querySelectorAll("input, select, textarea").forEach((control) => {
          control.disabled = !active;
        });
      });
    };
    form.dataset.scopeBound = "true";
    scope.addEventListener("change", update);
    update();
  });
}
