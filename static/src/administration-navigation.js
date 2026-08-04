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
  source?.classList.remove("is-drag-source-item");
  source?.querySelector(":scope > .navigation-tree__node")?.classList.remove("is-drag-source");
  tree.querySelectorAll(".navigation-tree__drop.is-active").forEach((zone) => {
    zone.classList.remove("is-active");
  });
}

function rememberNavigationFocus(nodeId) {
  try {
    window.sessionStorage.setItem("kaj.navigation-move-focus", nodeId);
  } catch {
    // Session storage is optional; the move still completes without focus restore.
  }
}

function restoreNavigationFocus(root = document) {
  let nodeId = null;
  try {
    nodeId = window.sessionStorage.getItem("kaj.navigation-move-focus");
    window.sessionStorage.removeItem("kaj.navigation-move-focus");
  } catch {
    return;
  }
  if (!nodeId) {
    return;
  }
  const handle = root.querySelector?.(
    `[data-navigation-node][data-node-id="${CSS.escape(nodeId)}"] .navigation-tree__handle`,
  );
  if (handle instanceof HTMLElement) {
    requestAnimationFrame(() => handle.focus({ preventScroll: true }));
  }
}

function siblingNavigationItems(item) {
  return Array.from(item.parentElement?.children ?? []).filter(
    (candidate) => candidate instanceof HTMLLIElement && candidate.hasAttribute("data-navigation-node"),
  );
}

function submitNavigationMove(form, source, targetParent, targetPosition) {
  const nodeId = source.dataset.nodeId ?? "";
  const nodeField = form.elements.namedItem("node_id");
  const parentField = form.elements.namedItem("new_parent_id");
  const positionField = form.elements.namedItem("new_position");
  if (
    !(nodeField instanceof HTMLInputElement) ||
    !(parentField instanceof HTMLInputElement) ||
    !(positionField instanceof HTMLInputElement) ||
    !nodeId
  ) {
    return false;
  }
  nodeField.value = nodeId;
  parentField.value = targetParent;
  positionField.value = String(targetPosition);
  rememberNavigationFocus(nodeId);
  form.requestSubmit();
  return true;
}

function keyboardNavigationMove(item, form, key) {
  const siblings = siblingNavigationItems(item);
  const sourceIndex = siblings.indexOf(item);
  if (sourceIndex < 0 || siblings.length < 2) {
    return false;
  }
  let targetIndex = sourceIndex;
  if (key === "ArrowUp") targetIndex -= 1;
  if (key === "ArrowDown") targetIndex += 1;
  if (key === "Home") targetIndex = 0;
  if (key === "End") targetIndex = siblings.length - 1;
  if (targetIndex < 0 || targetIndex >= siblings.length || targetIndex === sourceIndex) {
    return false;
  }
  const target = siblings[targetIndex];
  const targetPosition = Number.parseInt(target.dataset.position ?? "", 10);
  if (!Number.isInteger(targetPosition)) {
    return false;
  }
  return submitNavigationMove(form, item, item.dataset.parentId ?? "", targetPosition);
}

function navigationDropDestination(source, zone) {
  const sourceParent = source.dataset.parentId ?? "";
  const sourcePosition = Number.parseInt(source.dataset.position ?? "", 10);
  const targetParent = zone.dataset.parentId ?? "";
  let targetPosition = Number.parseInt(zone.dataset.position ?? "", 10);
  if (!Number.isInteger(sourcePosition) || !Number.isInteger(targetPosition)) {
    return null;
  }
  if (sourceParent === targetParent && sourcePosition < targetPosition) {
    targetPosition -= 1;
  }
  if (sourceParent === targetParent && sourcePosition === targetPosition) {
    return null;
  }
  return { targetParent, targetPosition };
}

function navigationDropPlacement(zone) {
  const owner = zone.closest("[data-navigation-node]");
  if (!(owner instanceof HTMLLIElement)) {
    return null;
  }
  if (zone.classList.contains("navigation-tree__drop--child")) {
    let list = owner.querySelector(":scope > .navigation-tree__children");
    let created = false;
    if (!(list instanceof HTMLOListElement)) {
      list = document.createElement("ol");
      list.className = "navigation-tree__children navigation-tree__children--preview";
      owner.insertBefore(list, zone);
      created = true;
    }
    return { list, reference: null, created };
  }
  const list = owner.parentElement;
  if (!(list instanceof HTMLOListElement)) {
    return null;
  }
  const isBefore = zone === owner.firstElementChild;
  return {
    list,
    reference: isBefore ? owner : owner.nextElementSibling,
    created: false,
  };
}

function navigationDropZoneDistance(zone, clientX, clientY) {
  const rect = zone.getBoundingClientRect();
  if (rect.width === 0 || rect.height === 0) {
    return null;
  }
  const horizontal = Math.max(rect.left - clientX, 0, clientX - rect.right);
  const vertical = Math.max(rect.top - clientY, 0, clientY - rect.bottom);
  return vertical + horizontal * 0.35;
}

function navigationDropZoneAtPoint(tree, source, clientX, clientY, currentZone = null) {
  if (!(source instanceof HTMLElement)) {
    return null;
  }
  const directHit = document.elementFromPoint(clientX, clientY);
  const directZone = directHit instanceof Element ? directHit.closest("[data-navigation-drop]") : null;
  if (directZone instanceof HTMLElement && !source.contains(directZone)) {
    return directZone;
  }
  const placeholder = tree.querySelector(".navigation-tree__item--placeholder");
  if (currentZone instanceof HTMLElement && placeholder instanceof HTMLElement) {
    const rect = placeholder.getBoundingClientRect();
    const retention = 8;
    if (
      clientX >= rect.left - retention &&
      clientX <= rect.right + retention &&
      clientY >= rect.top - retention &&
      clientY <= rect.bottom + retention
    ) {
      return currentZone;
    }
  }
  const treeRect = tree.getBoundingClientRect();
  const padding = 72;
  if (
    clientX < treeRect.left - padding ||
    clientX > treeRect.right + padding ||
    clientY < treeRect.top - padding ||
    clientY > treeRect.bottom + padding
  ) {
    return null;
  }
  let nearest = null;
  let nearestDistance = Number.POSITIVE_INFINITY;
  let currentDistance = null;
  tree.querySelectorAll("[data-navigation-drop]").forEach((candidate) => {
    if (!(candidate instanceof HTMLElement) || source.contains(candidate)) {
      return;
    }
    const distance = navigationDropZoneDistance(candidate, clientX, clientY);
    if (distance === null) {
      return;
    }
    if (candidate === currentZone) {
      currentDistance = distance;
    }
    if (distance < nearestDistance) {
      nearest = candidate;
      nearestDistance = distance;
    }
  });
  const switchMargin = 14;
  if (
    currentZone instanceof HTMLElement &&
    nearest !== currentZone &&
    currentDistance !== null &&
    nearestDistance + switchMargin >= currentDistance
  ) {
    return currentZone;
  }
  return nearest;
}

function initializeNavigationNodeDisclosure(node) {
  const toggle = node.querySelector(":scope > header [data-navigation-node-toggle]");
  const details = node.querySelector(":scope > [data-navigation-node-details]");
  if (!(toggle instanceof HTMLButtonElement) || !(details instanceof HTMLElement)) {
    return;
  }
  toggle.addEventListener("click", () => {
    const expanded = toggle.getAttribute("aria-expanded") !== "true";
    const label = toggle.dataset.navigationNodeLabel ?? "导航节点";
    toggle.setAttribute("aria-expanded", String(expanded));
    toggle.setAttribute("aria-label", `${expanded ? "收起" : "展开"}节点详情：${label}`);
    toggle.title = `${expanded ? "收起" : "展开"}节点详情`;
    details.hidden = !expanded;
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
    let pointerId = null;
    let pointerZone = null;
    let placeholder = null;
    let floatingNode = null;
    let sourceDisplay = "";
    let pointerOffset = { x: 0, y: 0 };
    const previewLists = new Set();

    const setPointerZone = (zone) => {
      if (pointerZone === zone) {
        return;
      }
      pointerZone?.classList.remove("is-active");
      pointerZone = zone;
      pointerZone?.classList.add("is-active");
    };

    const movePlaceholder = (zone) => {
      if (!(placeholder instanceof HTMLLIElement)) {
        return;
      }
      const placement = navigationDropPlacement(zone);
      if (!placement || (placement.list === source?.parentElement && placement.reference === source)) {
        return;
      }
      if (placement.created) {
        previewLists.add(placement.list);
      }
      if (placement.reference === placeholder) {
        return;
      }
      if (placement.reference === null) {
        if (placeholder.parentElement !== placement.list || placeholder !== placement.list.lastElementChild) {
          placement.list.appendChild(placeholder);
        }
        return;
      }
      if (placeholder.nextElementSibling !== placement.reference || placeholder.parentElement !== placement.list) {
        placement.list.insertBefore(placeholder, placement.reference);
      }
    };

    const moveFloatingNode = (clientX, clientY) => {
      if (!(floatingNode instanceof HTMLElement)) {
        return;
      }
      floatingNode.style.transform = `translate3d(${clientX - pointerOffset.x}px, ${clientY - pointerOffset.y}px, 0)`;
    };

    const clearPreview = (item, { restore = true } = {}) => {
      if (restore && item instanceof HTMLElement) {
        item.style.display = sourceDisplay;
      }
      placeholder?.remove();
      floatingNode?.remove();
      previewLists.forEach((list) => {
        if (list.childElementCount === 0) {
          list.remove();
        }
      });
      previewLists.clear();
      placeholder = null;
      floatingNode = null;
      sourceDisplay = "";
      pointerOffset = { x: 0, y: 0 };
      clearDragState(tree, item);
    };

    const beginPreview = (item, node, clientX, clientY) => {
      if (placeholder || floatingNode) {
        return;
      }
      const itemRect = item.getBoundingClientRect();
      const nodeRect = node.getBoundingClientRect();
      sourceDisplay = item.style.display;
      placeholder = document.createElement("li");
      placeholder.className = "navigation-tree__item navigation-tree__item--placeholder";
      placeholder.setAttribute("aria-hidden", "true");
      placeholder.style.height = `${itemRect.height}px`;
      item.style.display = "none";
      item.parentElement?.insertBefore(placeholder, item);

      floatingNode = node.cloneNode(true);
      floatingNode.classList.remove("is-drag-source");
      floatingNode.classList.add("navigation-tree__node--floating");
      floatingNode.setAttribute("aria-hidden", "true");
      floatingNode.querySelectorAll("[id]").forEach((element) => element.removeAttribute("id"));
      floatingNode.style.width = `${nodeRect.width}px`;
      floatingNode.style.left = "0px";
      floatingNode.style.top = "0px";
      document.body.appendChild(floatingNode);
      pointerOffset = {
        x: clientX - nodeRect.left,
        y: clientY - nodeRect.top,
      };
      moveFloatingNode(clientX, clientY);
      tree.classList.add("is-dragging");
      item.classList.add("is-drag-source-item");
    };

    const endPointerDrag = (handle, item, event, { submit } = { submit: false }) => {
      if (pointerId !== event.pointerId || source !== item) {
        return;
      }
      if (handle.hasPointerCapture?.(event.pointerId)) {
        handle.releasePointerCapture(event.pointerId);
      }
      const zone = pointerZone;
      pointerId = null;
      pointerZone = null;
      if (submit && zone instanceof HTMLElement) {
        const destination = navigationDropDestination(item, zone);
        clearPreview(item);
        source = null;
        if (destination) {
          submitNavigationMove(form, item, destination.targetParent, destination.targetPosition);
        }
      } else {
        clearPreview(item);
        source = null;
      }
      event.preventDefault();
    };

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
      initializeNavigationNodeDisclosure(node);
      handle.setAttribute("tabindex", "0");
      handle.setAttribute("role", "button");
      handle.addEventListener("keydown", (event) => {
        if (!(event instanceof KeyboardEvent) || !["ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) {
          return;
        }
        if (keyboardNavigationMove(item, form, event.key)) {
          event.preventDefault();
        }
      });
      handle.addEventListener("pointerdown", (event) => {
        if (!event.isPrimary || (event.pointerType === "mouse" && event.button !== 0)) {
          return;
        }
        source = item;
        pointerId = event.pointerId;
        pointerZone = null;
        beginPreview(item, node, event.clientX, event.clientY);
        handle.focus({ preventScroll: true });
        handle.setPointerCapture?.(event.pointerId);
        event.preventDefault();
      });
      handle.addEventListener("pointermove", (event) => {
        if (pointerId !== event.pointerId || source !== item) {
          return;
        }
        moveFloatingNode(event.clientX, event.clientY);
        const validZone = navigationDropZoneAtPoint(
          tree,
          item,
          event.clientX,
          event.clientY,
          pointerZone,
        );
        setPointerZone(validZone);
        if (validZone) {
          movePlaceholder(validZone);
        }
        event.preventDefault();
      });
      handle.addEventListener("pointerup", (event) => {
        endPointerDrag(handle, item, event, { submit: true });
      });
      handle.addEventListener("pointercancel", (event) => {
        endPointerDrag(handle, item, event, { submit: false });
      });
      handle.addEventListener("dragstart", (event) => {
        source = item;
        const rect = node.getBoundingClientRect();
        beginPreview(item, node, rect.left + rect.width / 2, rect.top + rect.height / 2);
        tree.classList.add("is-dragging");
        node.classList.add("is-drag-source");
        if (event.dataTransfer) {
          event.dataTransfer.effectAllowed = "move";
          event.dataTransfer.setData("text/plain", item.dataset.nodeId ?? "");
        }
      });
      handle.addEventListener("dragend", () => {
        clearPreview(source);
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
        const validZone = navigationDropZoneAtPoint(
          tree,
          source,
          event.clientX,
          event.clientY,
          pointerZone,
        ) ?? zone;
        setPointerZone(validZone);
        movePlaceholder(validZone);
        moveFloatingNode(event.clientX, event.clientY);
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
        const movedSource = source;
        source = null;
        const destination = navigationDropDestination(movedSource, zone);
        clearPreview(movedSource);
        if (destination) {
          submitNavigationMove(form, movedSource, destination.targetParent, destination.targetPosition);
        }
      });
    });
  });
  restoreNavigationFocus(root);
}

export {
  initializeNavigationTrees,
  initializeNodeForms,
};
