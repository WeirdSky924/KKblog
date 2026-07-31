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

function suggestedNavigationPosition(form) {
  const parent = form.querySelector("[data-navigation-parent]");
  const position = form.querySelector("[data-navigation-position]");
  if (!(parent instanceof HTMLSelectElement) || !(position instanceof HTMLInputElement)) {
    return null;
  }
  const nodeIdField = form.elements.namedItem("node_id");
  const currentNodeId = nodeIdField instanceof HTMLInputElement ? nodeIdField.value : "";
  const siblings = Array.from(
    form.ownerDocument.querySelectorAll("[data-navigation-node]"),
  ).filter(
    (node) =>
      node instanceof HTMLLIElement &&
      node.dataset.parentId === parent.value &&
      node.dataset.nodeId !== currentNodeId,
  );
  return { position, value: siblings.length };
}

function initializeNavigationPositionForms(root = document) {
  root.querySelectorAll?.("form[data-navigation-position-form]").forEach((form) => {
    if (
      !(form instanceof HTMLFormElement) ||
      form.dataset.navigationPositionBound === "true"
    ) {
      return;
    }
    const parent = form.querySelector("[data-navigation-parent]");
    if (!(parent instanceof HTMLSelectElement)) {
      return;
    }
    form.dataset.navigationPositionBound = "true";
    parent.addEventListener("change", () => {
      const suggestion = suggestedNavigationPosition(form);
      if (!suggestion) {
        return;
      }
      suggestion.position.value = String(suggestion.value);
      suggestion.position.dispatchEvent(new Event("input", { bubbles: true }));
    });
  });
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
  initializeNavigationPositionForms(root);
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

export {
  initializeNavigationTrees,
  initializeNodeForms,
};
