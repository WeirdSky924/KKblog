import {
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  CircleCheck,
  ChevronRight,
  Copy,
  Ellipsis,
  GripVertical,
  Heading1,
  Heading2,
  Heading3,
  Heading4,
  Heading5,
  Heading6,
  Info,
  List,
  ListOrdered,
  ListChecks,
  Minus,
  Pilcrow,
  Quote,
  Replace,
  SquareCode,
  Trash2,
  TriangleAlert,
  createIcons,
} from "lucide";

import {
  editorCommandState,
  editorCommandsForSurface,
  runEditorCommand,
} from "./editor-commands.js";
import {
  runTopLevelBlockOperation,
  selectTopLevelBlock,
  topLevelBlockAtIndex,
  topLevelBlockAtPosition,
} from "./editor-block-operations.js";
import { initializeEditorBlockDrag } from "./editor-block-drag.js";

export {
  runTopLevelBlockOperation,
  topLevelBlockAtPosition,
} from "./editor-block-operations.js";

const ICONS = {
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  CircleCheck,
  ChevronRight,
  Copy,
  Ellipsis,
  GripVertical,
  Heading1,
  Heading2,
  Heading3,
  Heading4,
  Heading5,
  Heading6,
  Info,
  List,
  ListOrdered,
  ListChecks,
  Minus,
  Pilcrow,
  Quote,
  Replace,
  SquareCode,
  Trash2,
  TriangleAlert,
};
const VIEWPORT_GUTTER = 8;
const MENU_GAP = 8;
let menuSequence = 0;

const actionDefinitions = [
  { id: "convert", label: "转换块类型", icon: "replace", submenu: true },
  { id: "copy", label: "复制当前块", icon: "copy" },
  { id: "up", label: "上移当前块", icon: "arrow-up" },
  { id: "down", label: "下移当前块", icon: "arrow-down" },
  { id: "delete", label: "删除当前块", icon: "trash-2", danger: true },
];

function clamp(value, minimum, maximum) {
  if (maximum < minimum) return minimum;
  return Math.min(Math.max(value, minimum), maximum);
}

export function blockMenuPosition({
  anchorLeft,
  anchorRight,
  anchorTop,
  anchorBottom,
  menuWidth,
  menuHeight,
  viewportLeft,
  viewportTop,
  viewportWidth,
  viewportHeight,
  clippingTop,
  clippingBottom,
  gutter = VIEWPORT_GUTTER,
  gap = MENU_GAP,
}) {
  const usableLeft = viewportLeft + gutter;
  const usableRight = viewportLeft + viewportWidth - gutter;
  const usableTop = Math.max(viewportTop + gutter, clippingTop + gutter);
  const usableBottom = Math.min(
    viewportTop + viewportHeight - gutter,
    clippingBottom - gutter,
  );
  const rightCandidate = anchorRight + gap;
  const leftCandidate = anchorLeft - gap - menuWidth;
  const left =
    rightCandidate + menuWidth <= usableRight
      ? rightCandidate
      : leftCandidate >= usableLeft
        ? leftCandidate
        : clamp(rightCandidate, usableLeft, usableRight - menuWidth);
  const belowTop = anchorBottom + gap;
  const availableBelow = Math.max(0, usableBottom - belowTop);
  const availableAbove = Math.max(0, anchorTop - gap - usableTop);
  const below =
    availableBelow >= menuHeight || availableBelow >= availableAbove;
  const maxHeight = Math.max(44, Math.floor(below ? availableBelow : availableAbove));
  const renderedHeight = Math.min(menuHeight, maxHeight);
  const top = below
    ? clamp(belowTop, usableTop, usableBottom - renderedHeight)
    : clamp(
        anchorTop - gap - renderedHeight,
        usableTop,
        usableBottom - renderedHeight,
      );
  return { left, top, maxHeight };
}

function icon(name) {
  const element = document.createElement("i");
  element.dataset.lucide = name;
  return element;
}

function menuButton({ id, label, iconName, disabled = false, danger = false }) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "author-block-menu__item";
  button.dataset.blockAction = id;
  button.setAttribute("role", "menuitem");
  button.disabled = disabled;
  if (danger) button.dataset.danger = "";
  button.append(icon(iconName));
  const copy = document.createElement("span");
  copy.textContent = label;
  button.append(copy);
  return button;
}

export function blockTypeLabelForDescriptor(descriptor, commands) {
  const node = descriptor?.node;
  if (!node) return null;
  const command = commands.find((candidate) => {
    if (candidate.active?.name !== node.type.name) return false;
    return Object.entries(candidate.active.attrs || {}).every(
      ([name, value]) => node.attrs?.[name] === value,
    );
  });
  return command?.label || null;
}

function blockTypeLabel(editor, descriptor, commands) {
  const descriptorLabel = blockTypeLabelForDescriptor(descriptor, commands);
  if (descriptorLabel) return descriptorLabel;
  const active = commands.find(
    (command) => editorCommandState(editor, command.id).active,
  );
  return active?.label || "当前块";
}

function renderMainMenu(menu, editor, descriptor, commands) {
  menu.replaceChildren();
  menu.setAttribute("aria-label", "块操作");
  const currentType = blockTypeLabel(editor, descriptor, commands);
  actionDefinitions.forEach((action) => {
    const disabled =
      (action.id === "up" && descriptor.index === 0) ||
      (action.id === "down" && descriptor.index === editor.state.doc.childCount - 1);
    const button = menuButton({
      id: action.id,
      label: action.label,
      iconName: action.icon,
      disabled,
      danger: action.danger,
    });
    if (action.id === "convert") {
      button.dataset.blockConvert = "";
      button.setAttribute("aria-haspopup", "menu");
      const meta = document.createElement("small");
      meta.textContent = currentType;
      button.append(meta, icon("chevron-right"));
    }
    menu.append(button);
  });
}

function renderTypeMenu(menu, editor, commands) {
  menu.replaceChildren();
  menu.setAttribute("aria-label", "转换块类型");
  const back = menuButton({
    id: "back",
    label: "返回块操作",
    iconName: "arrow-left",
  });
  menu.append(back);
  const separator = document.createElement("hr");
  separator.setAttribute("role", "separator");
  menu.append(separator);
  commands.forEach((command) => {
    const state = editorCommandState(editor, command.id);
    const button = menuButton({
      id: `command:${command.id}`,
      label: command.label,
      iconName: command.icon,
      disabled: state.disabled && !state.active,
    });
    button.dataset.editorCommand = command.id;
    button.setAttribute("role", "menuitemradio");
    button.setAttribute("aria-checked", String(state.active));
    menu.append(button);
  });
}

function createSurface(menuId) {
  const controls = document.createElement("div");
  controls.className = "author-block-controls";
  controls.dataset.editorBlockControls = "";
  controls.hidden = true;
  const drag = document.createElement("button");
  drag.type = "button";
  drag.className = "author-block-controls__button";
  drag.dataset.editorBlockDrag = "";
  drag.setAttribute("aria-label", "拖动当前块");
  drag.title = "拖动当前块；键盘排序请使用块菜单";
  drag.append(icon("grip-vertical"));
  const trigger = document.createElement("button");
  trigger.type = "button";
  trigger.className = "author-block-controls__button";
  trigger.dataset.editorBlockMenuTrigger = "";
  trigger.setAttribute("aria-label", "打开块操作");
  trigger.setAttribute("aria-haspopup", "menu");
  trigger.setAttribute("aria-expanded", "false");
  trigger.setAttribute("aria-controls", menuId);
  trigger.title = "块操作";
  trigger.append(icon("ellipsis"));
  controls.append(drag, trigger);

  const menu = document.createElement("div");
  menu.id = menuId;
  menu.className = "author-block-menu";
  menu.dataset.editorBlockMenu = "";
  menu.setAttribute("role", "menu");
  menu.hidden = true;
  return { controls, drag, trigger, menu };
}

function installIcons(root) {
  createIcons({
    root,
    icons: ICONS,
    attrs: {
      "aria-hidden": "true",
      focusable: "false",
      width: "20",
      height: "20",
    },
  });
}

export function initializeEditorBlockMenu({ root, editor }) {
  const host = root.querySelector(".author-tiptap");
  const content = editor?.view?.dom;
  if (!(host instanceof HTMLElement) || !(content instanceof HTMLElement)) {
    return { update() {}, dispose() {} };
  }

  const commands = editorCommandsForSurface("block");
  const menuId = `author-block-menu-${(menuSequence += 1)}`;
  const { controls, drag, trigger, menu } = createSurface(menuId);
  host.append(controls);
  document.body.append(menu);
  installIcons(controls);

  let frame = null;
  let hoveredIndex = null;
  let activeIndex = null;
  let mode = "main";
  let executing = false;

  const descriptorForSelection = () =>
    topLevelBlockAtPosition(editor.state.doc, editor.state.selection.from);
  const currentDescriptor = () => {
    const index = activeIndex ?? hoveredIndex;
    return index === null
      ? descriptorForSelection()
      : topLevelBlockAtIndex(editor.state.doc, index);
  };
  const blockElement = (descriptor) => {
    if (!descriptor) return null;
    const node = editor.view.nodeDOM(descriptor.from);
    if (node instanceof HTMLElement && node.parentElement === content) return node;
    return content.children.item(descriptor.index);
  };
  const hideControls = () => {
    controls.hidden = true;
    controls.removeAttribute("data-block-index");
    controls.style.removeProperty("top");
  };
  const positionControls = () => {
    frame = null;
    const descriptor = currentDescriptor();
    const ownsFocus =
      editor.isFocused ||
      hoveredIndex !== null ||
      controls.contains(document.activeElement) ||
      !menu.hidden;
    if (editor.isEditable === false || !ownsFocus || !descriptor) {
      hideControls();
      return;
    }
    const element = blockElement(descriptor);
    if (!(element instanceof HTMLElement)) {
      hideControls();
      return;
    }
    const rect = element.getBoundingClientRect();
    const hostRect = host.getBoundingClientRect();
    const headerBottom =
      document.querySelector("[data-site-header]")?.getBoundingClientRect().bottom ||
      0;
    const visibleTop = Math.max(hostRect.top, headerBottom);
    const visibleBottom = Math.min(hostRect.bottom, innerHeight);
    if (rect.bottom <= visibleTop || rect.top >= visibleBottom) {
      hideControls();
      return;
    }
    controls.hidden = false;
    controls.dataset.blockIndex = String(descriptor.index);
    controls.style.top = `${rect.top - hostRect.top + host.scrollTop}px`;
  };
  const schedule = () => {
    if (frame !== null) return;
    frame = window.requestAnimationFrame(positionControls);
  };

  const close = ({ restore = "none" } = {}) => {
    menu.hidden = true;
    menu.replaceChildren();
    menu.style.removeProperty("left");
    menu.style.removeProperty("top");
    menu.style.removeProperty("--author-block-menu-max-height");
    trigger.setAttribute("aria-expanded", "false");
    mode = "main";
    activeIndex = null;
    if (restore === "trigger" && !controls.hidden) trigger.focus();
    if (restore === "editor") editor.commands.focus();
    schedule();
  };
  const positionMenu = () => {
    if (menu.hidden) return;
    const anchor = trigger.getBoundingClientRect();
    const hostRect = host.getBoundingClientRect();
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
    menu.style.visibility = "hidden";
    const layout = blockMenuPosition({
      anchorLeft: anchor.left,
      anchorRight: anchor.right,
      anchorTop: anchor.top,
      anchorBottom: anchor.bottom,
      menuWidth: menu.offsetWidth,
      menuHeight: menu.scrollHeight,
      viewportLeft,
      viewportTop,
      viewportWidth,
      viewportHeight,
      clippingTop: Math.max(hostRect.top, headerBottom),
      clippingBottom: Math.min(hostRect.bottom, viewportTop + viewportHeight),
    });
    menu.style.left = `${layout.left}px`;
    menu.style.top = `${layout.top}px`;
    menu.style.setProperty(
      "--author-block-menu-max-height",
      `${layout.maxHeight}px`,
    );
    menu.style.removeProperty("visibility");
  };
  const focusFirst = (preferred = null) => {
    const buttons = Array.from(
      menu.querySelectorAll(".author-block-menu__item:not(:disabled)"),
    );
    const target = preferred
      ? buttons.find((button) => button.dataset.editorCommand === preferred)
      : null;
    (target || buttons[0])?.focus();
  };
  const render = () => {
    const descriptor = currentDescriptor();
    if (!descriptor) {
      close();
      return false;
    }
    if (mode === "types") {
      renderTypeMenu(menu, editor, commands);
    } else {
      renderMainMenu(menu, editor, descriptor, commands);
    }
    installIcons(menu);
    positionMenu();
    return true;
  };
  const open = (descriptor) => {
    if (!descriptor || editor.isEditable === false) return;
    activeIndex = descriptor.index;
    mode = "main";
    selectTopLevelBlock(editor, descriptor);
    menu.hidden = false;
    trigger.setAttribute("aria-expanded", "true");
    render();
    window.requestAnimationFrame(() => focusFirst());
  };

  const descriptorFromTarget = (target) => {
    let element = target instanceof Element ? target : null;
    while (element && element.parentElement !== content) {
      element = element.parentElement;
    }
    if (!element) return null;
    const index = Array.from(content.children).indexOf(element);
    return topLevelBlockAtIndex(editor.state.doc, index);
  };
  const hover = (event) => {
    const descriptor = descriptorFromTarget(event.target);
    if (!descriptor || descriptor.index === hoveredIndex) return;
    hoveredIndex = descriptor.index;
    schedule();
  };
  const leaveContent = (event) => {
    if (controls.contains(event.relatedTarget)) return;
    hoveredIndex = null;
    schedule();
  };
  const leaveControls = (event) => {
    if (content.contains(event.relatedTarget) || !menu.hidden) return;
    hoveredIndex = null;
    schedule();
  };
  const preserveSelection = (event) => event.preventDefault();
  const activateControl = (event) => {
    const button = event.target.closest?.("button");
    if (!(button instanceof HTMLButtonElement) || !controls.contains(button)) return;
    const descriptor = currentDescriptor();
    if (!descriptor) return;
    if (button === drag) {
      selectTopLevelBlock(editor, descriptor);
      schedule();
      return;
    }
    if (!menu.hidden) {
      close({ restore: "trigger" });
      return;
    }
    open(descriptor);
  };

  const activateMenu = (event) => {
    const button = event.target.closest?.("[data-block-action]");
    if (!(button instanceof HTMLButtonElement) || !menu.contains(button)) return;
    const action = button.dataset.blockAction;
    if (action === "convert") {
      mode = "types";
      render();
      focusFirst(
        commands.find((command) => editorCommandState(editor, command.id).active)?.id,
      );
      return;
    }
    if (action === "back") {
      mode = "main";
      render();
      menu.querySelector("[data-block-convert]")?.focus();
      return;
    }
    const descriptor = currentDescriptor();
    if (!descriptor) return;
    executing = true;
    let ran;
    if (action.startsWith("command:")) {
      const commandId = action.slice("command:".length);
      ran = runEditorCommand(editor, commandId, {
        skipCommandWhenActive: true,
        prepareChain:
          descriptor.node.type.name === "callout" &&
          !commandId.startsWith("callout-")
            ? (chain) => chain.lift("callout")
            : null,
      });
    } else {
      ran = runTopLevelBlockOperation(editor, descriptor, action);
    }
    executing = false;
    if (ran) close({ restore: "editor" });
  };

  const moveFocus = (direction) => {
    const buttons = Array.from(
      menu.querySelectorAll(".author-block-menu__item:not(:disabled)"),
    );
    if (!buttons.length) return;
    const current = buttons.indexOf(document.activeElement);
    const index =
      direction === "first"
        ? 0
        : direction === "last"
          ? buttons.length - 1
          : (current + direction + buttons.length) % buttons.length;
    buttons[index].focus();
    buttons[index].scrollIntoView({ block: "nearest", inline: "nearest" });
  };
  const handleKeys = (event) => {
    if (menu.hidden || !menu.contains(event.target)) return;
    if (event.key === "Escape") {
      event.preventDefault();
      if (mode === "types") {
        mode = "main";
        render();
        menu.querySelector("[data-block-convert]")?.focus();
      } else {
        close({ restore: "trigger" });
      }
      return;
    }
    if (event.key === "ArrowLeft" && mode === "types") {
      event.preventDefault();
      mode = "main";
      render();
      menu.querySelector("[data-block-convert]")?.focus();
      return;
    }
    if (
      event.key === "ArrowRight" &&
      event.target.closest?.("[data-block-convert]")
    ) {
      event.preventDefault();
      mode = "types";
      render();
      focusFirst();
      return;
    }
    const directions = { ArrowDown: 1, ArrowUp: -1, Home: "first", End: "last" };
    if (!(event.key in directions)) return;
    event.preventDefault();
    moveFocus(directions[event.key]);
  };
  const closeOutside = (event) => {
    if (menu.hidden || menu.contains(event.target) || controls.contains(event.target)) {
      return;
    }
    close();
  };
  const handleTransaction = ({ transaction }) => {
    if (transaction.docChanged) hoveredIndex = null;
    if (!menu.hidden && transaction.docChanged && !executing) close();
    schedule();
  };
  const reposition = () => {
    schedule();
    positionMenu();
  };
  const dragController = initializeEditorBlockDrag({
    host,
    content,
    dragHandle: drag,
    editor,
    getDescriptor: currentDescriptor,
    getBlockElement: blockElement,
    onDragStart() {
      if (!menu.hidden) close();
    },
    onDragEnd: schedule,
  });

  controls.addEventListener("mousedown", preserveSelection);
  controls.addEventListener("click", activateControl);
  controls.addEventListener("pointerleave", leaveControls);
  menu.addEventListener("mousedown", preserveSelection);
  menu.addEventListener("click", activateMenu);
  menu.addEventListener("keydown", handleKeys);
  content.addEventListener("pointermove", hover);
  content.addEventListener("pointerleave", leaveContent);
  document.addEventListener("pointerdown", closeOutside);
  document.addEventListener("focusin", schedule);
  window.addEventListener("resize", reposition);
  window.addEventListener("scroll", reposition, true);
  window.visualViewport?.addEventListener("resize", reposition);
  window.visualViewport?.addEventListener("scroll", reposition);
  editor.on("selectionUpdate", schedule);
  editor.on("transaction", handleTransaction);
  editor.on("focus", schedule);
  editor.on("blur", schedule);
  schedule();

  return {
    update: schedule,
    dispose() {
      dragController.dispose();
      if (frame !== null) window.cancelAnimationFrame(frame);
      controls.removeEventListener("mousedown", preserveSelection);
      controls.removeEventListener("click", activateControl);
      controls.removeEventListener("pointerleave", leaveControls);
      menu.removeEventListener("mousedown", preserveSelection);
      menu.removeEventListener("click", activateMenu);
      menu.removeEventListener("keydown", handleKeys);
      content.removeEventListener("pointermove", hover);
      content.removeEventListener("pointerleave", leaveContent);
      document.removeEventListener("pointerdown", closeOutside);
      document.removeEventListener("focusin", schedule);
      window.removeEventListener("resize", reposition);
      window.removeEventListener("scroll", reposition, true);
      window.visualViewport?.removeEventListener("resize", reposition);
      window.visualViewport?.removeEventListener("scroll", reposition);
      editor.off("selectionUpdate", schedule);
      editor.off("transaction", handleTransaction);
      editor.off("focus", schedule);
      editor.off("blur", schedule);
      controls.remove();
      menu.remove();
    },
  };
}
