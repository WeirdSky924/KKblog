import { moveTopLevelBlock } from "./editor-block-operations.js";

const DRAG_THRESHOLD = 6;
const DROP_HYSTERESIS = 12;
const AUTO_SCROLL_EDGE = 48;
const AUTO_SCROLL_MAX = 16;

function clamp(value, minimum, maximum) {
  return Math.min(Math.max(value, minimum), maximum);
}

export function stableBlockDropIndex({
  pointerY,
  currentIndex,
  midpoints,
  hysteresis = DROP_HYSTERESIS,
}) {
  const points = Array.isArray(midpoints)
    ? midpoints.filter(Number.isFinite)
    : [];
  if (!Number.isFinite(pointerY)) return clamp(currentIndex || 0, 0, points.length);

  const retained = clamp(
    Number.isInteger(currentIndex) ? currentIndex : 0,
    0,
    points.length,
  );
  const lower = retained === 0 ? Number.NEGATIVE_INFINITY : points[retained - 1];
  const upper = retained === points.length ? Number.POSITIVE_INFINITY : points[retained];
  if (pointerY >= lower - hysteresis && pointerY <= upper + hysteresis) {
    return retained;
  }

  const next = points.findIndex((midpoint) => pointerY < midpoint);
  return next === -1 ? points.length : next;
}

export function blockPreviewOrder(blockCount, sourceIndex, targetIndex) {
  if (
    !Number.isInteger(blockCount) ||
    blockCount < 1 ||
    !Number.isInteger(sourceIndex) ||
    sourceIndex < 0 ||
    sourceIndex >= blockCount
  ) {
    return [];
  }
  const remaining = Array.from({ length: blockCount }, (_, index) => index).filter(
    (index) => index !== sourceIndex,
  );
  remaining.splice(clamp(targetIndex, 0, remaining.length), 0, sourceIndex);
  return remaining;
}

export function boundedBlockAutoScrollVelocity({
  pointerY,
  top,
  bottom,
  edge = AUTO_SCROLL_EDGE,
  maximum = AUTO_SCROLL_MAX,
}) {
  if (
    ![pointerY, top, bottom, edge, maximum].every(Number.isFinite) ||
    bottom <= top ||
    edge <= 0 ||
    maximum <= 0
  ) {
    return 0;
  }
  if (pointerY < top + edge) {
    return -maximum * clamp((top + edge - pointerY) / edge, 0, 1);
  }
  if (pointerY > bottom - edge) {
    return maximum * clamp((pointerY - (bottom - edge)) / edge, 0, 1);
  }
  return 0;
}

function stripCloneIdentity(root) {
  root.removeAttribute("id");
  root.removeAttribute("name");
  root.querySelectorAll("[id]").forEach((element) => element.removeAttribute("id"));
  root
    .querySelectorAll("[name]")
    .forEach((element) => element.removeAttribute("name"));
  root.querySelectorAll("a, button, input, select, textarea, [tabindex]").forEach(
    (element) => element.setAttribute("tabindex", "-1"),
  );
}

export function initializeEditorBlockDrag({
  host,
  content,
  dragHandle,
  editor,
  getDescriptor,
  getBlockElement,
  onDragStart = () => {},
  onDragEnd = () => {},
}) {
  let pointerId = null;
  let startPoint = null;
  let latestPoint = null;
  let descriptor = null;
  let sourceElement = null;
  let sourceRect = null;
  let floating = null;
  let placeholder = null;
  let preview = null;
  let previewElements = [];
  let frame = null;
  let focusFrame = null;
  let active = false;
  let targetIndex = null;
  let pointerOffsetY = 0;
  let floatingLeft = 0;
  let suppressClick = false;
  let suppressClickTimer = null;
  const previewAnimations = new Map();
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  const topLevelElements = () =>
    Array.from(content.children).filter((element) => element instanceof HTMLElement);

  const cancelAnimations = () => {
    previewAnimations.forEach((animation) => animation.cancel());
    previewAnimations.clear();
  };

  const positionPreview = () => {
    if (!preview) return;
    const rect = content.getBoundingClientRect();
    const hostRect = host.getBoundingClientRect();
    preview.style.left = `${rect.left - hostRect.left + host.scrollLeft}px`;
    preview.style.top = `${rect.top - hostRect.top + host.scrollTop}px`;
    preview.style.width = `${rect.width}px`;
    preview.style.minHeight = `${rect.height}px`;
  };

  const applyOrder = (nextTarget) => {
    const order = blockPreviewOrder(
      previewElements.length,
      descriptor.index,
      nextTarget,
    );
    if (!order.length) return;
    const previousTops = new Map(
      previewElements.map((element) => [element, element.getBoundingClientRect().top]),
    );
    order.forEach((originalIndex, visualIndex) => {
      previewElements[originalIndex].style.order = String(visualIndex);
    });
    targetIndex = nextTarget;
    if (reduceMotion.matches) return;

    previewElements.forEach((element) => {
      if (element === placeholder || typeof element.animate !== "function") return;
      const delta = previousTops.get(element) - element.getBoundingClientRect().top;
      if (Math.abs(delta) < 0.5) return;
      previewAnimations.get(element)?.cancel();
      const animation = element.animate(
        [
          { transform: `translate3d(0, ${delta}px, 0)` },
          { transform: "translate3d(0, 0, 0)" },
        ],
        { duration: 150, easing: "cubic-bezier(0.2, 0, 0, 1)" },
      );
      previewAnimations.set(element, animation);
      animation.addEventListener("finish", () => previewAnimations.delete(element), {
        once: true,
      });
    });
  };

  const updateTarget = () => {
    if (!active || previewElements.length !== editor.state.doc.childCount) return;
    const remaining = previewElements.filter(
      (_, index) => index !== descriptor.index,
    );
    const midpoint =
      latestPoint.y - pointerOffsetY + sourceRect.height / 2;
    const nextTarget = stableBlockDropIndex({
      pointerY: midpoint,
      currentIndex: targetIndex,
      midpoints: remaining.map((element) => {
        const rect = element.getBoundingClientRect();
        return rect.top + rect.height / 2;
      }),
    });
    if (nextTarget !== targetIndex) applyOrder(nextTarget);
  };

  const visibleBounds = () => {
    const rect = host.getBoundingClientRect();
    const viewport = window.visualViewport;
    const viewportTop = viewport?.offsetTop || 0;
    const viewportBottom = viewportTop + (viewport?.height || innerHeight);
    const headerBottom =
      document.querySelector("[data-site-header]")?.getBoundingClientRect().bottom ||
      viewportTop;
    return {
      top: Math.max(rect.top, headerBottom, viewportTop),
      bottom: Math.min(rect.bottom, viewportBottom),
    };
  };

  const renderFrame = () => {
    frame = null;
    if (!active || !latestPoint) return;
    const bounds = visibleBounds();
    const floatingTop = clamp(
      latestPoint.y - pointerOffsetY,
      bounds.top,
      Math.max(bounds.top, bounds.bottom - floating.offsetHeight),
    );
    floating.style.transform = `translate3d(${floatingLeft}px, ${floatingTop}px, 0)`;
    updateTarget();
    positionPreview();
    const velocity = boundedBlockAutoScrollVelocity({
      pointerY: latestPoint.y,
      top: bounds.top,
      bottom: bounds.bottom,
    });
    const previousScroll = host.scrollTop;
    host.scrollTop = clamp(
      previousScroll + velocity,
      0,
      Math.max(0, host.scrollHeight - host.clientHeight),
    );
    if (host.scrollTop !== previousScroll) {
      frame = window.requestAnimationFrame(renderFrame);
    }
  };

  const schedule = () => {
    if (frame === null) frame = window.requestAnimationFrame(renderFrame);
  };

  const beginPreview = () => {
    const elements = topLevelElements();
    if (elements.length !== editor.state.doc.childCount) return;
    sourceRect = sourceElement.getBoundingClientRect();
    targetIndex = descriptor.index;
    pointerOffsetY = startPoint.y - sourceRect.top;
    floatingLeft = sourceRect.left;

    preview = document.createElement("div");
    preview.className = "author-block-drag__preview author-tiptap__content";
    preview.setAttribute("aria-hidden", "true");
    previewElements = elements.map((element, index) => {
      if (index === descriptor.index) {
        placeholder = document.createElement("div");
        placeholder.className = "author-block-drag__placeholder";
        placeholder.style.height = `${sourceRect.height}px`;
        const styles = getComputedStyle(sourceElement);
        placeholder.style.marginBlockStart = styles.marginBlockStart;
        placeholder.style.marginBlockEnd = styles.marginBlockEnd;
        placeholder.style.marginInlineStart = styles.marginInlineStart;
        placeholder.style.marginInlineEnd = styles.marginInlineEnd;
        return placeholder;
      }
      const clone = element.cloneNode(true);
      stripCloneIdentity(clone);
      return clone;
    });
    preview.append(...previewElements);
    host.append(preview);

    floating = document.createElement("div");
    floating.className = "author-block-drag__floating author-tiptap__content";
    floating.setAttribute("aria-hidden", "true");
    const clone = sourceElement.cloneNode(true);
    stripCloneIdentity(clone);
    floating.append(clone);
    floating.style.width = `${sourceRect.width}px`;
    floating.style.minHeight = `${sourceRect.height}px`;
    document.body.append(floating);

    content.classList.add("is-block-dragging");
    host.classList.add("is-block-dragging");
    positionPreview();
    active = true;
    onDragStart();
    schedule();
  };

  const clearPreview = () => {
    if (frame !== null) window.cancelAnimationFrame(frame);
    frame = null;
    cancelAnimations();
    content.classList.remove("is-block-dragging");
    host.classList.remove("is-block-dragging");
    floating?.remove();
    preview?.remove();
    floating = null;
    placeholder = null;
    preview = null;
    previewElements = [];
    active = false;
  };

  const resetPointer = () => {
    pointerId = null;
    startPoint = null;
    latestPoint = null;
    descriptor = null;
    sourceElement = null;
    sourceRect = null;
    targetIndex = null;
    pointerOffsetY = 0;
    floatingLeft = 0;
  };

  const finish = ({ commit, focusHandle = false } = {}) => {
    if (pointerId === null) return;
    const capturedPointerId = pointerId;
    const movedDescriptor = descriptor;
    const destination = targetIndex;
    const wasActive = active;
    pointerId = null;
    try {
      if (dragHandle.hasPointerCapture?.(capturedPointerId)) {
        dragHandle.releasePointerCapture(capturedPointerId);
      }
    } catch {
      // Pointer capture may already be released by the browser.
    }
    clearPreview();
    resetPointer();
    if (commit && wasActive && destination !== movedDescriptor.index) {
      moveTopLevelBlock(editor, movedDescriptor, destination);
    } else if (focusHandle) {
      focusFrame = window.requestAnimationFrame(() => {
        focusFrame = null;
        if (dragHandle.offsetParent !== null) {
          dragHandle.focus({ preventScroll: true });
        } else {
          editor.commands.focus();
        }
      });
    }
    onDragEnd();
  };

  const pointerDown = (event) => {
    if (
      pointerId !== null ||
      editor.isEditable === false ||
      !event.isPrimary ||
      (event.pointerType === "mouse" && event.button !== 0)
    ) {
      return;
    }
    descriptor = getDescriptor();
    sourceElement = getBlockElement(descriptor);
    if (!descriptor || !(sourceElement instanceof HTMLElement)) return;
    pointerId = event.pointerId;
    startPoint = { x: event.clientX, y: event.clientY };
    latestPoint = { ...startPoint };
    dragHandle.focus({ preventScroll: true });
    try {
      dragHandle.setPointerCapture?.(pointerId);
    } catch {
      // Synthetic pointer tests and older touch engines may not expose capture.
    }
    event.preventDefault();
  };

  const pointerMove = (event) => {
    if (event.pointerId !== pointerId) return;
    latestPoint = { x: event.clientX, y: event.clientY };
    if (!active) {
      const distance = Math.hypot(
        latestPoint.x - startPoint.x,
        latestPoint.y - startPoint.y,
      );
      if (distance < DRAG_THRESHOLD) return;
      beginPreview();
    }
    schedule();
    event.preventDefault();
  };

  const pointerUp = (event) => {
    if (event.pointerId !== pointerId) return;
    if (active) {
      suppressClick = true;
      window.clearTimeout(suppressClickTimer);
      suppressClickTimer = window.setTimeout(() => {
        suppressClick = false;
        suppressClickTimer = null;
      }, 0);
    }
    finish({ commit: true, focusHandle: !active });
    event.preventDefault();
  };
  const pointerCancel = (event) => {
    if (event.pointerId !== pointerId) return;
    finish({ commit: false, focusHandle: true });
  };
  const lostPointerCapture = (event) => {
    if (event.pointerId === pointerId) {
      finish({ commit: false, focusHandle: true });
    }
  };
  const keyDown = (event) => {
    if (event.key !== "Escape" || pointerId === null) return;
    event.preventDefault();
    finish({ commit: false, focusHandle: true });
  };
  const suppressDraggedClick = (event) => {
    if (!suppressClick) return;
    suppressClick = false;
    event.preventDefault();
    event.stopImmediatePropagation();
  };
  const cancelOnDocumentChange = ({ transaction }) => {
    if (pointerId !== null && transaction.docChanged) {
      finish({ commit: false, focusHandle: true });
    }
  };

  dragHandle.addEventListener("pointerdown", pointerDown);
  dragHandle.addEventListener("pointermove", pointerMove);
  dragHandle.addEventListener("pointerup", pointerUp);
  dragHandle.addEventListener("pointercancel", pointerCancel);
  dragHandle.addEventListener("lostpointercapture", lostPointerCapture);
  dragHandle.addEventListener("click", suppressDraggedClick, true);
  document.addEventListener("keydown", keyDown);
  editor.on("transaction", cancelOnDocumentChange);

  return {
    dispose() {
      finish({ commit: false });
      if (focusFrame !== null) window.cancelAnimationFrame(focusFrame);
      window.clearTimeout(suppressClickTimer);
      dragHandle.removeEventListener("pointerdown", pointerDown);
      dragHandle.removeEventListener("pointermove", pointerMove);
      dragHandle.removeEventListener("pointerup", pointerUp);
      dragHandle.removeEventListener("pointercancel", pointerCancel);
      dragHandle.removeEventListener("lostpointercapture", lostPointerCapture);
      dragHandle.removeEventListener("click", suppressDraggedClick, true);
      document.removeEventListener("keydown", keyDown);
      editor.off("transaction", cancelOnDocumentChange);
    },
  };
}
