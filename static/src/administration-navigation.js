function updateNodeTargetFields(form) {
  const type = form.querySelector("[name='node_type']")?.value;
  const urlGroup = form.querySelector("[data-navigation-target='url']");
  const sectionGroup = form.querySelector("[data-navigation-target='section']");
  const urlField = urlGroup?.querySelector("input");
  const sectionField = sectionGroup?.querySelector("select");
  const usesSection = type === "SECTION";
  if (urlGroup instanceof HTMLElement) {
    urlGroup.hidden = usesSection;
  }
  if (sectionGroup instanceof HTMLElement) {
    sectionGroup.hidden = !usesSection;
  }
  if (urlField instanceof HTMLInputElement) {
    urlField.disabled = usesSection;
  }
  if (sectionField instanceof HTMLSelectElement) {
    sectionField.disabled = !usesSection;
  }
}

function initializeNodeForms(root = document) {
  root.querySelectorAll?.("form[data-navigation-node-form]").forEach((form) => {
    if (!(form instanceof HTMLFormElement) || form.dataset.navigationBound === "true") {
      return;
    }
    form.dataset.navigationBound = "true";
    const type = form.querySelector("[name='node_type']");
    type?.addEventListener("change", () => updateNodeTargetFields(form));
    updateNodeTargetFields(form);
  });
}

function clearDragState(tree, source) {
  tree.classList.remove("is-dragging");
  source?.querySelector(":scope > .navigation-tree__node")?.classList.remove("is-drag-source");
  tree.querySelectorAll(".navigation-tree__drop.is-active").forEach((zone) => {
    zone.classList.remove("is-active");
  });
}

function initializeNavigationTrees(root = document) {
  root.querySelectorAll?.("[data-navigation-tree]").forEach((tree) => {
    if (!(tree instanceof HTMLOListElement) || tree.dataset.dragBound === "true") {
      return;
    }
    const form = document.querySelector("form[data-navigation-drag-form]");
    if (!(form instanceof HTMLFormElement)) {
      return;
    }
    tree.dataset.dragBound = "true";
    let source = null;

    tree.querySelectorAll("[data-navigation-node]").forEach((item) => {
      const node = item.querySelector(":scope > .navigation-tree__node");
      const handle = node?.querySelector(".navigation-tree__handle");
      if (
        !(item instanceof HTMLLIElement) ||
        !(node instanceof HTMLElement) ||
        !(handle instanceof HTMLElement)
      ) {
        return;
      }
      handle.addEventListener("dragstart", (event) => {
        source = item;
        tree.classList.add("is-dragging");
        node.classList.add("is-drag-source");
        if (event.dataTransfer) {
          event.dataTransfer.effectAllowed = "move";
          event.dataTransfer.setData("text/plain", item.dataset.nodeId ?? "");
        }
      });
      handle.addEventListener("dragend", () => {
        clearDragState(tree, source);
        source = null;
      });
    });

    tree.querySelectorAll("[data-navigation-drop]").forEach((zone) => {
      if (!(zone instanceof HTMLElement)) {
        return;
      }
      zone.addEventListener("dragover", (event) => {
        if (!source || source.contains(zone)) {
          return;
        }
        event.preventDefault();
        zone.classList.add("is-active");
        if (event.dataTransfer) {
          event.dataTransfer.dropEffect = "move";
        }
      });
      zone.addEventListener("dragleave", () => zone.classList.remove("is-active"));
      zone.addEventListener("drop", (event) => {
        event.preventDefault();
        if (!source || source.contains(zone)) {
          return;
        }
        const sourceParent = source.dataset.parentId ?? "";
        const sourcePosition = Number.parseInt(source.dataset.position ?? "", 10);
        const targetParent = zone.dataset.parentId ?? "";
        let targetPosition = Number.parseInt(zone.dataset.position ?? "", 10);
        if (!Number.isInteger(sourcePosition) || !Number.isInteger(targetPosition)) {
          return;
        }
        if (sourceParent === targetParent && sourcePosition < targetPosition) {
          targetPosition -= 1;
        }
        if (sourceParent === targetParent && sourcePosition === targetPosition) {
          clearDragState(tree, source);
          source = null;
          return;
        }
        form.elements.node_id.value = source.dataset.nodeId ?? "";
        form.elements.new_parent_id.value = targetParent;
        form.elements.new_position.value = String(targetPosition);
        form.requestSubmit();
      });
    });
  });
}

function initializeSiteSubmenus(root = document) {
  root.querySelectorAll?.("[data-site-submenu-toggle]").forEach((button) => {
    if (!(button instanceof HTMLButtonElement) || button.dataset.submenuBound === "true") {
      return;
    }
    button.dataset.submenuBound = "true";
    button.addEventListener("click", () => {
      const targetId = button.getAttribute("aria-controls");
      const submenu = targetId ? document.getElementById(targetId) : null;
      if (!(submenu instanceof HTMLElement)) {
        return;
      }
      const expanded = button.getAttribute("aria-expanded") === "true";
      button.setAttribute("aria-expanded", expanded ? "false" : "true");
      const label = button.dataset.submenuLabel ?? "子菜单";
      button.setAttribute("aria-label", `${expanded ? "展开" : "收起"}${label}`);
      button.setAttribute("title", `${expanded ? "展开" : "收起"}${label}`);
      submenu.hidden = expanded;
    });
  });
}

export {
  initializeNavigationTrees,
  initializeNodeForms,
  initializeSiteSubmenus,
};
