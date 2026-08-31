import {
  Bold,
  CircleCheck,
  Code,
  CornerDownLeft,
  Ellipsis,
  Heading1,
  Heading2,
  Heading3,
  Heading4,
  Heading5,
  Heading6,
  Italic,
  Info,
  Link,
  List,
  ListOrdered,
  ListChecks,
  Minus,
  Pilcrow,
  Quote,
  Redo2,
  RemoveFormatting,
  SquareCode,
  SquarePlay,
  Sigma,
  Strikethrough,
  Table2,
  TriangleAlert,
  Underline,
  Undo2,
  createIcons,
} from "lucide";

import {
  editorCommandState,
  editorCommandsForSurface,
  runEditorCommand,
} from "./editor-commands.js";

const ICONS = {
  Bold,
  CircleCheck,
  Code,
  CornerDownLeft,
  Ellipsis,
  Heading1,
  Heading2,
  Heading3,
  Heading4,
  Heading5,
  Heading6,
  Italic,
  Info,
  Link,
  List,
  ListOrdered,
  ListChecks,
  Minus,
  Pilcrow,
  Quote,
  Redo2,
  RemoveFormatting,
  SquareCode,
  SquarePlay,
  Sigma,
  Strikethrough,
  Table2,
  TriangleAlert,
  Underline,
  Undo2,
};
const groupLabels = {
  text: "文字格式",
  structure: "段落结构",
  history: "编辑历史",
};
const MENU_VIEWPORT_GUTTER = 8;
const MENU_TRIGGER_GAP = 1;

function commandButton(
  command,
  { menu = false, menuRole = "checkbox" } = {},
) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = menu
    ? "author-tiptap-toolbar__menu-command"
    : "author-tiptap-toolbar__command";
  button.dataset.editorCommand = command.id;
  button.dataset.commandCompact = command.compact;
  button.dataset.commandPlacement = command.toolbarPlacement;
  button.dataset.commandSurface = menu ? "menu" : "toolbar";
  button.setAttribute("aria-label", command.label);
  button.title = command.shortcut
    ? `${command.label} · ${command.shortcut}`
    : command.label;
  if (menu) {
    button.setAttribute("role", `menuitem${menuRole}`);
    button.setAttribute("aria-checked", "false");
  } else {
    button.setAttribute("aria-pressed", "false");
  }
  const icon = document.createElement("i");
  icon.dataset.lucide = command.icon;
  button.append(icon);
  if (menu) {
    const label = document.createElement("span");
    label.textContent = command.label;
    button.append(label);
  }
  return button;
}

function disclosure({ className, label, icon, commands, menuRole }) {
  const root = document.createElement("details");
  root.className = className;
  root.dataset.editorDisclosure = "";
  const summary = document.createElement("summary");
  summary.setAttribute("role", "button");
  summary.setAttribute("aria-label", label);
  summary.setAttribute("aria-expanded", "false");
  summary.setAttribute("aria-haspopup", "menu");
  summary.title = label;
  const summaryIcon = document.createElement("i");
  summaryIcon.dataset.lucide = icon;
  summary.append(summaryIcon);
  if (className.includes("block-type")) {
    const summaryLabel = document.createElement("span");
    summaryLabel.dataset.editorBlockLabel = "";
    summaryLabel.textContent = "正文";
    summary.append(summaryLabel);
  }
  const panel = document.createElement("div");
  panel.className = "author-tiptap-toolbar__menu";
  panel.setAttribute("role", "menu");
  panel.setAttribute("aria-label", label);
  commands.forEach((command) =>
    panel.append(
      commandButton(command, {
        menu: true,
        menuRole,
      }),
    ),
  );
  root.append(summary, panel);
  return { root, panel, summary };
}

function moveMenuFocus(panel, direction) {
  const buttons = Array.from(
    panel.querySelectorAll("[data-editor-command]:not(:disabled)"),
  ).filter((button) => getComputedStyle(button).display !== "none");
  if (!buttons.length) return;
  const current = buttons.indexOf(document.activeElement);
  const next =
    direction === "first"
      ? 0
      : direction === "last"
        ? buttons.length - 1
        : (current + direction + buttons.length) % buttons.length;
  buttons[next].focus();
  buttons[next].scrollIntoView({ block: "nearest", inline: "nearest" });
}

export function editorMenuLayout({
  panelHeight,
  summaryTop,
  summaryBottom,
  viewportHeight,
  boundaryTop = 0,
  boundaryBottom = viewportHeight,
  gutter = MENU_VIEWPORT_GUTTER,
}) {
  const usableTop = Math.max(gutter, boundaryTop + gutter);
  const usableBottom = Math.min(
    viewportHeight - gutter,
    boundaryBottom - gutter,
  );
  const availableAbove = Math.max(0, summaryTop - usableTop - MENU_TRIGGER_GAP);
  const availableBelow = Math.max(
    0,
    usableBottom - summaryBottom - MENU_TRIGGER_GAP,
  );
  const direction =
    panelHeight > availableBelow && availableAbove > availableBelow ? "up" : "down";
  return {
    direction,
    maxHeight: Math.max(
      44,
      Math.floor(direction === "up" ? availableAbove : availableBelow),
    ),
  };
}

function positionDisclosureMenu({ root, panel, summary }) {
  if (!root.open) {
    root.removeAttribute("data-menu-direction");
    root.style.removeProperty("--author-menu-max-height");
    return;
  }

  const summaryRect = summary.getBoundingClientRect();
  const clippingContainer = root.closest(".author-editor-pane");
  const clippingRect = clippingContainer?.getBoundingClientRect();
  const layout = editorMenuLayout({
    panelHeight: panel.scrollHeight,
    summaryTop: summaryRect.top,
    summaryBottom: summaryRect.bottom,
    viewportHeight: document.documentElement.clientHeight,
    boundaryTop: clippingRect?.top,
    boundaryBottom: clippingRect?.bottom,
  });
  root.dataset.menuDirection = layout.direction;
  root.style.setProperty("--author-menu-max-height", `${layout.maxHeight}px`);
}

function toolbarOverflowPriority(button) {
  if (button.dataset.commandCompact === "primary") return 2;
  if (button.dataset.commandPlacement === "primary") return 1;
  return 0;
}

function updateToolbarGroupVisibility(toolbar) {
  toolbar.querySelectorAll(".author-tiptap-toolbar__group").forEach((group) => {
    group.hidden = !group.querySelector(
      '[data-command-surface="toolbar"]:not([hidden])',
    );
  });
}

function layoutToolbarOverflow(toolbar, more) {
  if (!more) return;
  const toolbarButtons = Array.from(
    toolbar.querySelectorAll('[data-command-surface="toolbar"]'),
  );
  const menuButtons = new Map(
    Array.from(
      more.panel.querySelectorAll('[data-command-surface="menu"]'),
    ).map((button) => [button.dataset.editorCommand, button]),
  );

  toolbarButtons.forEach((button) => {
    button.hidden = false;
  });
  menuButtons.forEach((button) => {
    button.hidden = true;
  });
  updateToolbarGroupVisibility(toolbar);
  more.root.hidden = true;
  more.root.open = false;
  more.summary.setAttribute("aria-expanded", "false");
  more.summary.setAttribute("aria-label", "更多格式");
  more.summary.title = "更多格式";

  if (toolbar.clientWidth <= 0 || toolbar.scrollWidth <= toolbar.clientWidth) return;

  more.root.hidden = false;
  const candidates = toolbarButtons
    .map((button, index) => ({ button, index }))
    .sort(
      (left, right) =>
        toolbarOverflowPriority(left.button) -
          toolbarOverflowPriority(right.button) || right.index - left.index,
    );
  let overflowCount = 0;
  for (const { button } of candidates) {
    button.hidden = true;
    const menuButton = menuButtons.get(button.dataset.editorCommand);
    if (menuButton) menuButton.hidden = false;
    overflowCount += 1;
    updateToolbarGroupVisibility(toolbar);
    if (toolbar.scrollWidth <= toolbar.clientWidth) break;
  }
  const label = `更多格式，${overflowCount} 项`;
  more.summary.setAttribute("aria-label", label);
  more.summary.title = label;
}

function renderToolbar(toolbar) {
  const toolbarCommands = editorCommandsForSurface("toolbar");
  const blockCommands = toolbarCommands.filter(
    (command) => command.presentation === "block-type",
  );
  const buttonCommands = toolbarCommands.filter(
    (command) => command.presentation === "button",
  );
  const disclosures = [];

  if (blockCommands.length) {
    const blockType = disclosure({
      className: "author-tiptap-toolbar__block-type",
      label: "段落格式",
      icon: "pilcrow",
      commands: blockCommands,
      menuRole: "radio",
    });
    toolbar.append(blockType.root);
    disclosures.push(blockType);
  }

  Object.keys(groupLabels).forEach((group) => {
    const commands = buttonCommands.filter((command) => command.group === group);
    if (!commands.length) return;
    const container = document.createElement("div");
    container.className = "author-tiptap-toolbar__group";
    container.dataset.commandGroup = group;
    container.setAttribute("role", "group");
    container.setAttribute("aria-label", groupLabels[group]);
    commands.forEach((command) => container.append(commandButton(command)));
    toolbar.append(container);
  });

  let more = null;
  if (buttonCommands.length) {
    more = disclosure({
      className: "author-tiptap-toolbar__more",
      label: "更多格式",
      icon: "ellipsis",
      commands: buttonCommands,
      menuRole: "checkbox",
    });
    more.root.dataset.editorMore = "";
    toolbar.append(more.root);
    disclosures.push(more);
  }

  createIcons({
    root: toolbar,
    icons: ICONS,
    attrs: {
      "aria-hidden": "true",
      focusable: "false",
      width: "24",
      height: "24",
    },
  });
  return { toolbarCommands, blockCommands, disclosures, more };
}

export function initializeEditorToolbar({ root, editor, actions = {} }) {
  const toolbar = root.querySelector("[data-editor-toolbar]");
  if (!(toolbar instanceof HTMLElement)) {
    return { update() {}, dispose() {} };
  }
  toolbar.replaceChildren();
  const { toolbarCommands, blockCommands, disclosures, more } =
    renderToolbar(toolbar);
  let toolbarLayoutFrame = null;
  let selectionBookmark = null;
  const rememberSelection = () => {
    try {
      selectionBookmark = editor.state.selection.getBookmark();
    } catch {
      selectionBookmark = null;
    }
  };
  const restoreSelection = () => {
    if (!selectionBookmark) return;
    try {
      editor.view.dispatch(
        editor.state.tr
          .setSelection(selectionBookmark.resolve(editor.state.doc))
          .setMeta("addToHistory", false),
      );
    } catch {
      selectionBookmark = null;
    }
  };
  const layoutToolbar = () => {
    toolbarLayoutFrame = null;
    layoutToolbarOverflow(toolbar, more);
  };
  const scheduleToolbarLayout = () => {
    if (toolbarLayoutFrame !== null) return;
    toolbarLayoutFrame = window.requestAnimationFrame(layoutToolbar);
  };
  const update = () => {
    const states = new Map(
      toolbarCommands.map((command) => [
        command.id,
        editorCommandState(editor, command.id),
      ]),
    );
    toolbar.querySelectorAll("[data-editor-command]").forEach((button) => {
      const state = states.get(button.dataset.editorCommand);
      button.disabled = state.disabled;
      if (button.dataset.commandSurface === "menu") {
        button.setAttribute("aria-checked", String(state.active));
      } else {
        button.setAttribute("aria-pressed", String(state.active));
      }
    });
    const activeBlock = blockCommands.find((command) => states.get(command.id).active);
    const blockDisclosure = toolbar.querySelector(
      ".author-tiptap-toolbar__block-type",
    );
    const blockLabel = blockDisclosure?.querySelector("[data-editor-block-label]");
    const summary = blockDisclosure?.querySelector("summary");
    const label = activeBlock?.label || "正文";
    if (blockLabel) blockLabel.textContent = label;
    if (summary) {
      summary.setAttribute("aria-label", `段落格式：${label}`);
      summary.title = `段落格式：${label}`;
    }
  };
  const activate = (event) => {
    const button = event.target.closest?.("[data-editor-command]");
    if (!(button instanceof HTMLButtonElement) || !toolbar.contains(button)) return;
    restoreSelection();
    if (
      runEditorCommand(editor, button.dataset.editorCommand, {
        actions,
        trigger: button,
      })
    ) {
      button.closest("details")?.removeAttribute("open");
      update();
    }
  };
  const preserveSelection = (event) => {
    if (event.target.closest?.("[data-editor-command], summary")) {
      rememberSelection();
      event.preventDefault();
    }
  };
  const handleKeys = (event) => {
    const current = disclosures.find(
      ({ root: disclosureRoot }) => disclosureRoot.contains(event.target),
    );
    if (!current) return;
    const { root: disclosureRoot, panel, summary } = current;
    if (
      event.target === summary &&
      (event.key === "ArrowDown" || event.key === "ArrowUp")
    ) {
      event.preventDefault();
      disclosureRoot.open = true;
      update();
      moveMenuFocus(panel, event.key === "ArrowDown" ? "first" : "last");
      return;
    }
    if (!disclosureRoot.open) return;
    if (event.key === "Escape") {
      event.preventDefault();
      disclosureRoot.open = false;
      summary.focus();
      return;
    }
    if (!panel.contains(event.target)) return;
    const directions = { ArrowDown: 1, ArrowUp: -1, Home: "first", End: "last" };
    if (!(event.key in directions)) return;
    event.preventDefault();
    moveMenuFocus(panel, directions[event.key]);
  };
  const closeOutside = (event) => {
    if (toolbar.contains(event.target)) return;
    disclosures.forEach(({ root: disclosureRoot }) => {
      disclosureRoot.open = false;
    });
  };
  const toggleListeners = disclosures.map((current) => {
    const listener = () => {
      current.summary.setAttribute("aria-expanded", String(current.root.open));
      if (current.root.open) {
        disclosures.forEach(({ root: disclosureRoot }) => {
          if (disclosureRoot !== current.root) disclosureRoot.open = false;
        });
        update();
      }
      positionDisclosureMenu(current);
    };
    current.root.addEventListener("toggle", listener);
    return { current, listener };
  });
  const positionOpenMenus = () => {
    disclosures.forEach((current) => positionDisclosureMenu(current));
  };
  const handleWindowResize = () => {
    scheduleToolbarLayout();
    positionOpenMenus();
  };
  const toolbarResizeObserver =
    "ResizeObserver" in window
      ? new ResizeObserver(scheduleToolbarLayout)
      : null;
  toolbarResizeObserver?.observe(toolbar);
  toolbar.addEventListener("mousedown", preserveSelection);
  toolbar.addEventListener("click", activate);
  toolbar.addEventListener("keydown", handleKeys);
  editor.on("selectionUpdate", rememberSelection);
  rememberSelection();
  document.addEventListener("click", closeOutside);
  window.addEventListener("resize", handleWindowResize);
  window.addEventListener("scroll", positionOpenMenus, true);
  update();
  layoutToolbar();
  return {
    update,
    dispose() {
      if (toolbarLayoutFrame !== null) {
        window.cancelAnimationFrame(toolbarLayoutFrame);
      }
      toolbarResizeObserver?.disconnect();
      toolbar.removeEventListener("mousedown", preserveSelection);
      toolbar.removeEventListener("click", activate);
      toolbar.removeEventListener("keydown", handleKeys);
      editor.off("selectionUpdate", rememberSelection);
      document.removeEventListener("click", closeOutside);
      window.removeEventListener("resize", handleWindowResize);
      window.removeEventListener("scroll", positionOpenMenus, true);
      toggleListeners.forEach(({ current, listener }) =>
        current.root.removeEventListener("toggle", listener),
      );
    },
  };
}
