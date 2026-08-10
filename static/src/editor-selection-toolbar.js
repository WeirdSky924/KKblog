import {
  Bold,
  Code,
  Italic,
  Link,
  RemoveFormatting,
  Strikethrough,
  Underline,
  createIcons,
} from "lucide";

import {
  editorCommandState,
  editorCommandsForSurface,
  runEditorCommand,
} from "./editor-commands.js";

const ICONS = {
  Bold,
  Code,
  Italic,
  Link,
  RemoveFormatting,
  Strikethrough,
  Underline,
};
const VIEWPORT_GUTTER = 8;
const SELECTION_GAP = 8;

function clamp(value, minimum, maximum) {
  if (maximum < minimum) return (minimum + maximum) / 2;
  return Math.min(Math.max(value, minimum), maximum);
}

export function selectionToolbarPosition({
  selectionTop,
  selectionBottom,
  selectionLeft,
  selectionRight,
  toolbarWidth,
  toolbarHeight,
  viewportLeft,
  viewportTop,
  viewportWidth,
  viewportHeight,
  clippingTop,
  clippingBottom,
  gutter = VIEWPORT_GUTTER,
  gap = SELECTION_GAP,
}) {
  const usableLeft = viewportLeft + gutter;
  const usableRight = viewportLeft + viewportWidth - gutter;
  const usableTop = Math.max(viewportTop + gutter, clippingTop + gutter);
  const usableBottom = Math.min(
    viewportTop + viewportHeight - gutter,
    clippingBottom - gutter,
  );
  const effectiveWidth = Math.min(toolbarWidth, usableRight - usableLeft);
  const halfWidth = effectiveWidth / 2;
  const left = clamp(
    (selectionLeft + selectionRight) / 2,
    usableLeft + halfWidth,
    usableRight - halfWidth,
  );
  const availableAbove = selectionTop - usableTop - gap;
  const availableBelow = usableBottom - selectionBottom - gap;
  const placement =
    availableAbove >= toolbarHeight || availableAbove >= availableBelow
      ? "above"
      : "below";
  const top =
    placement === "above"
      ? clamp(
          selectionTop - gap,
          usableTop + toolbarHeight,
          usableBottom,
        )
      : clamp(
          selectionBottom + gap,
          usableTop,
          usableBottom - toolbarHeight,
        );
  return { left, top, placement };
}

function commandButton(command) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "author-selection-toolbar__command";
  button.dataset.editorCommand = command.id;
  button.setAttribute("aria-label", command.label);
  button.setAttribute("aria-pressed", "false");
  button.title = command.shortcut
    ? `${command.label} · ${command.shortcut}`
    : command.label;
  const icon = document.createElement("i");
  icon.dataset.lucide = command.icon;
  button.append(icon);
  return button;
}

function selectionRect(editor) {
  const { from, to } = editor.state.selection;
  const start = editor.view.coordsAtPos(from);
  const end = editor.view.coordsAtPos(to);
  return {
    top: Math.min(start.top, end.top),
    bottom: Math.max(start.bottom, end.bottom),
    left: Math.min(start.left, end.left),
    right: Math.max(start.right, end.right),
  };
}

export function initializeEditorSelectionToolbar({ root, editor, actions = {} }) {
  const host = root.querySelector(".author-tiptap");
  if (!(host instanceof HTMLElement)) {
    return { update() {}, dispose() {} };
  }
  const commands = editorCommandsForSurface("bubble");
  const toolbar = document.createElement("div");
  toolbar.className = "author-selection-toolbar";
  toolbar.dataset.editorSelectionToolbar = "";
  toolbar.setAttribute("role", "toolbar");
  toolbar.setAttribute("aria-label", "选区格式");
  toolbar.hidden = true;
  commands.forEach((command) => toolbar.append(commandButton(command)));
  host.append(toolbar);
  createIcons({
    root: toolbar,
    icons: ICONS,
    attrs: {
      "aria-hidden": "true",
      focusable: "false",
      width: "20",
      height: "20",
    },
  });

  let frame = null;
  let dismissedSelection = null;
  let lastSelection = null;

  const key = () => {
    const { from, to } = editor.state.selection;
    return `${from}:${to}`;
  };
  const hide = () => {
    toolbar.hidden = true;
    toolbar.style.removeProperty("left");
    toolbar.style.removeProperty("top");
    toolbar.style.removeProperty("visibility");
    toolbar.removeAttribute("data-placement");
  };
  const updateStates = () => {
    toolbar.querySelectorAll("[data-editor-command]").forEach((button) => {
      const state = editorCommandState(editor, button.dataset.editorCommand);
      button.disabled = state.disabled;
      button.setAttribute("aria-pressed", String(state.active));
    });
  };
  const update = () => {
    frame = null;
    const selection = editor.state.selection;
    const currentSelection = key();
    if (currentSelection !== lastSelection) {
      dismissedSelection = null;
      lastSelection = currentSelection;
    }
    const linkDialogOpen = Boolean(
      document.querySelector("[data-editor-link-dialog][open]"),
    );
    const ownsFocus =
      editor.isFocused ||
      toolbar.contains(document.activeElement) ||
      linkDialogOpen;
    const selectedText = selection.empty
      ? ""
      : editor.state.doc.textBetween(selection.from, selection.to, "");
    if (
      editor.isEditable === false ||
      !ownsFocus ||
      !selectedText ||
      dismissedSelection === currentSelection
    ) {
      hide();
      return;
    }

    const rect = selectionRect(editor);
    const clippingRect = host.getBoundingClientRect();
    const visualViewport = window.visualViewport;
    const viewportLeft = visualViewport?.offsetLeft || 0;
    const viewportTop = visualViewport?.offsetTop || 0;
    const viewportWidth =
      visualViewport?.width || document.documentElement.clientWidth;
    const viewportHeight =
      visualViewport?.height || document.documentElement.clientHeight;
    const headerBottom =
      document.querySelector("[data-site-header]")?.getBoundingClientRect().bottom ||
      viewportTop;
    const clippingTop = Math.max(clippingRect.top, headerBottom);
    const clippingBottom = Math.min(
      clippingRect.bottom,
      viewportTop + viewportHeight,
    );
    if (rect.bottom <= clippingTop || rect.top >= clippingBottom) {
      hide();
      return;
    }

    toolbar.hidden = false;
    toolbar.style.visibility = "hidden";
    updateStates();
    const position = selectionToolbarPosition({
      selectionTop: rect.top,
      selectionBottom: rect.bottom,
      selectionLeft: rect.left,
      selectionRight: rect.right,
      toolbarWidth: toolbar.offsetWidth,
      toolbarHeight: toolbar.offsetHeight,
      viewportLeft,
      viewportTop,
      viewportWidth,
      viewportHeight,
      clippingTop,
      clippingBottom,
    });
    toolbar.dataset.placement = position.placement;
    toolbar.style.left = `${position.left}px`;
    toolbar.style.top = `${position.top}px`;
    toolbar.style.removeProperty("visibility");
  };
  const schedule = () => {
    if (frame !== null) return;
    frame = window.requestAnimationFrame(update);
  };
  const activate = (event) => {
    const button = event.target.closest?.("[data-editor-command]");
    if (!(button instanceof HTMLButtonElement) || !toolbar.contains(button)) return;
    if (
      runEditorCommand(editor, button.dataset.editorCommand, {
        actions,
        trigger: button,
      })
    ) {
      schedule();
    }
  };
  const preserveSelection = (event) => {
    if (event.target.closest?.("[data-editor-command]")) event.preventDefault();
  };
  const dismiss = (event) => {
    if (
      event.key !== "Escape" ||
      toolbar.hidden ||
      (!editor.view.dom.contains(event.target) && !toolbar.contains(event.target))
    ) {
      return;
    }
    event.preventDefault();
    dismissedSelection = key();
    hide();
    editor.commands.focus();
  };

  toolbar.addEventListener("mousedown", preserveSelection);
  toolbar.addEventListener("click", activate);
  host.addEventListener("keydown", dismiss);
  document.addEventListener("focusin", schedule);
  window.addEventListener("resize", schedule);
  window.addEventListener("scroll", schedule, true);
  window.visualViewport?.addEventListener("resize", schedule);
  window.visualViewport?.addEventListener("scroll", schedule);
  editor.on("selectionUpdate", schedule);
  editor.on("transaction", schedule);
  editor.on("focus", schedule);
  editor.on("blur", schedule);
  schedule();

  return {
    update: schedule,
    dispose() {
      if (frame !== null) window.cancelAnimationFrame(frame);
      toolbar.removeEventListener("mousedown", preserveSelection);
      toolbar.removeEventListener("click", activate);
      host.removeEventListener("keydown", dismiss);
      document.removeEventListener("focusin", schedule);
      window.removeEventListener("resize", schedule);
      window.removeEventListener("scroll", schedule, true);
      window.visualViewport?.removeEventListener("resize", schedule);
      window.visualViewport?.removeEventListener("scroll", schedule);
      editor.off("selectionUpdate", schedule);
      editor.off("transaction", schedule);
      editor.off("focus", schedule);
      editor.off("blur", schedule);
      toolbar.remove();
    },
  };
}
