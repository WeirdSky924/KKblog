import {
  CircleCheck,
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
  SquareCode,
  Table2,
  TriangleAlert,
  createIcons,
} from "lucide";

import {
  editorCommandState,
  editorCommandsForSurface,
  runEditorCommand,
} from "./editor-commands.js";

const ICONS = {
  CircleCheck,
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
  SquareCode,
  Table2,
  TriangleAlert,
};
const VIEWPORT_GUTTER = 8;
const ANCHOR_GAP = 8;
let menuSequence = 0;

function clamp(value, minimum, maximum) {
  if (maximum < minimum) return minimum;
  return Math.min(Math.max(value, minimum), maximum);
}

function normalizedQuery(value) {
  return String(value || "")
    .normalize("NFKC")
    .toLocaleLowerCase("zh-CN")
    .trim();
}

export function filterSlashCommands(commands, query) {
  const needle = normalizedQuery(query);
  if (!needle) return [...commands];
  return commands.filter((command) =>
    normalizedQuery(
      [command.label, command.description, ...command.aliases].join(" "),
    ).includes(needle),
  );
}

export function slashMenuPosition({
  anchorLeft,
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
  gap = ANCHOR_GAP,
}) {
  const usableLeft = viewportLeft + gutter;
  const usableRight = viewportLeft + viewportWidth - gutter;
  const usableTop = Math.max(viewportTop + gutter, clippingTop + gutter);
  const usableBottom = Math.min(
    viewportTop + viewportHeight - gutter,
    clippingBottom - gutter,
  );
  const effectiveWidth = Math.min(menuWidth, usableRight - usableLeft);
  const left = clamp(anchorLeft, usableLeft, usableRight - effectiveWidth);
  const availableAbove = Math.max(0, anchorTop - usableTop - gap);
  const availableBelow = Math.max(0, usableBottom - anchorBottom - gap);
  const placement =
    availableBelow >= menuHeight || availableBelow >= availableAbove
      ? "below"
      : "above";
  const available = placement === "below" ? availableBelow : availableAbove;
  const maxHeight = Math.max(44, Math.floor(available));
  const renderedHeight = Math.min(menuHeight, maxHeight);
  const top =
    placement === "below"
      ? clamp(anchorBottom + gap, usableTop, usableBottom - renderedHeight)
      : clamp(
          anchorTop - gap - renderedHeight,
          usableTop,
          usableBottom - renderedHeight,
        );
  return { left, top, placement, maxHeight };
}

function slashTrigger(editor) {
  const selection = editor.state.selection;
  if (!selection.empty) return null;
  const { $from } = selection;
  if ($from.parent.type.name !== "paragraph") return null;
  const before = $from.parent.textBetween(0, $from.parentOffset, "\n", "\n");
  const after = $from.parent.textBetween(
    $from.parentOffset,
    $from.parent.content.size,
    "\n",
    "\n",
  );
  if (
    after ||
    !before.startsWith("/") ||
    before.slice(1).includes("/") ||
    before.length > 41
  ) {
    return null;
  }
  return {
    from: $from.start(),
    to: selection.from,
    query: before.slice(1),
    key: `${$from.start()}:${before}`,
  };
}

function optionElement(command, menuId, index) {
  const option = document.createElement("button");
  option.type = "button";
  option.id = `${menuId}-option-${index}`;
  option.className = "author-slash-menu__option";
  option.dataset.editorCommand = command.id;
  option.setAttribute("role", "option");
  option.setAttribute("aria-selected", "false");
  option.tabIndex = -1;
  const icon = document.createElement("i");
  icon.dataset.lucide = command.icon;
  const copy = document.createElement("span");
  const label = document.createElement("strong");
  label.textContent = command.label;
  const description = document.createElement("small");
  description.textContent = command.description;
  copy.append(label, description);
  option.append(icon, copy);
  return option;
}

export function initializeEditorSlashMenu({ root, editor }) {
  const host = root.querySelector(".author-tiptap");
  if (!(host instanceof HTMLElement)) {
    return { update() {}, dispose() {} };
  }
  const commands = editorCommandsForSurface("slash");
  const menuId = `author-slash-menu-${(menuSequence += 1)}`;
  const menu = document.createElement("div");
  menu.id = menuId;
  menu.className = "author-slash-menu";
  menu.dataset.editorSlashMenu = "";
  menu.setAttribute("role", "listbox");
  menu.setAttribute("aria-label", "块命令");
  menu.hidden = true;
  host.append(menu);

  let frame = null;
  let currentTrigger = null;
  let filtered = [];
  let activeIndex = -1;
  let activeCommandId = null;
  let dismissedTrigger = null;

  const close = () => {
    menu.hidden = true;
    menu.replaceChildren();
    menu.style.removeProperty("left");
    menu.style.removeProperty("top");
    menu.style.removeProperty("--author-slash-max-height");
    menu.removeAttribute("data-placement");
    editor.view.dom.setAttribute("aria-expanded", "false");
    editor.view.dom.removeAttribute("aria-controls");
    editor.view.dom.removeAttribute("aria-activedescendant");
    currentTrigger = null;
    filtered = [];
    activeIndex = -1;
    activeCommandId = null;
  };
  const setActive = (index, step = 1) => {
    if (!filtered.length) {
      activeIndex = -1;
      activeCommandId = null;
      editor.view.dom.removeAttribute("aria-activedescendant");
      return;
    }
    const options = Array.from(menu.querySelectorAll("[role=option]"));
    if (!options.some((option) => !option.disabled)) {
      activeIndex = -1;
      activeCommandId = null;
      editor.view.dom.removeAttribute("aria-activedescendant");
      return;
    }
    let next = (index + filtered.length) % filtered.length;
    for (let count = 0; count < filtered.length; count += 1) {
      const candidate = options[next];
      if (candidate && !candidate.disabled) break;
      next = (next + step + filtered.length) % filtered.length;
    }
    activeIndex = next;
    activeCommandId = filtered[activeIndex].id;
    menu.querySelectorAll("[role=option]").forEach((option, optionIndex) => {
      const selected = optionIndex === activeIndex;
      option.setAttribute("aria-selected", String(selected));
      if (selected) {
        editor.view.dom.setAttribute("aria-activedescendant", option.id);
        option.scrollIntoView({ block: "nearest", inline: "nearest" });
      }
    });
  };
  const render = () => {
    menu.replaceChildren();
    if (!filtered.length) {
      const empty = document.createElement("p");
      empty.className = "author-slash-menu__empty";
      empty.setAttribute("role", "status");
      empty.textContent = "没有匹配的块";
      menu.append(empty);
      setActive(-1);
      return;
    }
    filtered.forEach((command, index) => {
      const option = optionElement(command, menuId, index);
      const range = { from: currentTrigger.from, to: currentTrigger.to };
      const state = editorCommandState(editor, command.id, {
        prepareChain: (chain) => chain.deleteRange(range),
        skipCommandWhenActive: true,
      });
      option.disabled = state.disabled;
      option.setAttribute("aria-disabled", String(state.disabled));
      menu.append(option);
    });
    createIcons({
      root: menu,
      icons: ICONS,
      attrs: {
        "aria-hidden": "true",
        focusable: "false",
        width: "20",
        height: "20",
      },
    });
    const preservedIndex = filtered.findIndex(
      (command) => command.id === activeCommandId,
    );
    setActive(preservedIndex >= 0 ? preservedIndex : 0);
  };
  const position = () => {
    if (menu.hidden || !currentTrigger) return;
    const anchor = editor.view.coordsAtPos(currentTrigger.to);
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
    if (anchor.bottom <= clippingTop || anchor.top >= clippingBottom) {
      menu.hidden = true;
      return;
    }
    menu.hidden = false;
    menu.style.visibility = "hidden";
    const layout = slashMenuPosition({
      anchorLeft: anchor.left,
      anchorTop: anchor.top,
      anchorBottom: anchor.bottom,
      menuWidth: menu.offsetWidth,
      menuHeight: menu.scrollHeight,
      viewportLeft,
      viewportTop,
      viewportWidth,
      viewportHeight,
      clippingTop,
      clippingBottom,
    });
    menu.dataset.placement = layout.placement;
    menu.style.left = `${layout.left}px`;
    menu.style.top = `${layout.top}px`;
    menu.style.setProperty(
      "--author-slash-max-height",
      `${layout.maxHeight}px`,
    );
    menu.style.removeProperty("visibility");
  };
  const refresh = () => {
    frame = null;
    const trigger = slashTrigger(editor);
    if (
      !trigger ||
      editor.isEditable === false ||
      !editor.isFocused ||
      dismissedTrigger === trigger.key
    ) {
      close();
      return;
    }
    if (dismissedTrigger && dismissedTrigger !== trigger.key) {
      dismissedTrigger = null;
    }
    currentTrigger = trigger;
    filtered = filterSlashCommands(commands, trigger.query);
    render();
    menu.hidden = false;
    editor.view.dom.setAttribute("aria-expanded", "true");
    editor.view.dom.setAttribute("aria-controls", menuId);
    position();
  };
  const schedule = () => {
    if (frame !== null) return;
    frame = window.requestAnimationFrame(refresh);
  };
  const execute = () => {
    const command = filtered[activeIndex];
    if (!command || !currentTrigger) {
      return false;
    }
    const range = { from: currentTrigger.from, to: currentTrigger.to };
    if (
      editorCommandState(editor, command.id, {
        prepareChain: (chain) => chain.deleteRange(range),
        skipCommandWhenActive: true,
      }).disabled
    ) {
      return false;
    }
    const ran = runEditorCommand(editor, command.id, {
      prepareChain: (chain) => chain.deleteRange(range),
      skipCommandWhenActive: true,
    });
    if (ran) {
      dismissedTrigger = null;
      close();
    }
    return ran;
  };
  const handleKeys = (event) => {
    if (menu.hidden || event.isComposing || editor.view.composing) return;
    if (event.key === "Escape") {
      event.preventDefault();
      dismissedTrigger = currentTrigger?.key || null;
      close();
      editor.commands.focus();
      return;
    }
    const direction = {
      ArrowDown: { index: activeIndex + 1, step: 1 },
      ArrowUp: { index: activeIndex - 1, step: -1 },
      Home: { index: 0, step: 1 },
      End: { index: filtered.length - 1, step: -1 },
    }[event.key];
    if (direction && filtered.length) {
      event.preventDefault();
      setActive(direction.index, direction.step);
      return;
    }
    if (event.key === "Enter" && filtered[activeIndex]) {
      event.preventDefault();
      execute();
    }
  };
  const preserveSelection = (event) => {
    if (event.target.closest?.("[data-editor-command]")) event.preventDefault();
  };
  const activate = (event) => {
    const option = event.target.closest?.("[data-editor-command]");
    if (!(option instanceof HTMLButtonElement) || !menu.contains(option)) return;
    activeIndex = filtered.findIndex(
      (command) => command.id === option.dataset.editorCommand,
    );
    execute();
  };
  const closeOnOutsideFocus = (event) => {
    if (editor.view.dom.contains(event.target) || menu.contains(event.target)) return;
    dismissedTrigger = currentTrigger?.key || dismissedTrigger;
    close();
  };

  host.addEventListener("keydown", handleKeys, true);
  menu.addEventListener("mousedown", preserveSelection);
  menu.addEventListener("click", activate);
  document.addEventListener("focusin", closeOnOutsideFocus);
  window.addEventListener("resize", schedule);
  window.addEventListener("scroll", schedule, true);
  window.visualViewport?.addEventListener("resize", schedule);
  window.visualViewport?.addEventListener("scroll", schedule);
  editor.on("transaction", schedule);
  editor.on("focus", schedule);
  editor.on("blur", schedule);

  return {
    update: schedule,
    dispose() {
      if (frame !== null) window.cancelAnimationFrame(frame);
      host.removeEventListener("keydown", handleKeys, true);
      menu.removeEventListener("mousedown", preserveSelection);
      menu.removeEventListener("click", activate);
      document.removeEventListener("focusin", closeOnOutsideFocus);
      window.removeEventListener("resize", schedule);
      window.removeEventListener("scroll", schedule, true);
      window.visualViewport?.removeEventListener("resize", schedule);
      window.visualViewport?.removeEventListener("scroll", schedule);
      editor.off("transaction", schedule);
      editor.off("focus", schedule);
      editor.off("blur", schedule);
      menu.remove();
    },
  };
}
