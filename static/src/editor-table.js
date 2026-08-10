import {
  Table,
  TableCell,
  TableHeader,
  TableRow,
} from "@tiptap/extension-table";
import { Extension } from "@tiptap/core";
import { Plugin } from "@tiptap/pm/state";
import {
  ArrowDownToLine,
  ArrowLeftToLine,
  ArrowRightToLine,
  ArrowUpToLine,
  Columns3,
  PanelTop,
  Rows3,
  Trash2,
  createIcons,
} from "lucide";

import {
  editorCommandState,
  editorCommandsForSurface,
  runEditorCommand,
} from "./editor-commands.js";
import { authorTableDocumentWithinLimits } from "./editor-table-contract.js";

const VIEWPORT_GUTTER = 8;
const TOOLBAR_GAP = 8;
const CELL_DEFAULTS = Object.freeze({
  colspan: 1,
  rowspan: 1,
  colwidth: null,
  align: null,
});
const ICONS = {
  ArrowDownToLine,
  ArrowLeftToLine,
  ArrowRightToLine,
  ArrowUpToLine,
  Columns3,
  PanelTop,
  Rows3,
  Trash2,
};

function announceTableLimit() {
  document.dispatchEvent(
    new CustomEvent("kaj:feedback", {
      detail: {
        key: "author-table-limit",
        level: "error",
        message: "表格最多 50 行、20 列，且不支持嵌套或合并单元格。",
        timeout: 5500,
      },
    }),
  );
}

const AuthorTableContract = Extension.create({
  name: "authorTableContract",
  addProseMirrorPlugins() {
    return [
      new Plugin({
        props: {
          handlePaste(_view, _event, slice) {
            if (authorTableDocumentWithinLimits(slice.content)) return false;
            announceTableLimit();
            return true;
          },
        },
        filterTransaction(transaction) {
          if (
            !transaction.docChanged ||
            authorTableDocumentWithinLimits(transaction.doc)
          ) {
            return true;
          }
          announceTableLimit();
          return false;
        },
      }),
    ];
  },
});

export function createAuthorTableExtensions() {
  return [
    AuthorTableContract,
    Table.configure({
      allowTableNodeSelection: true,
      resizable: false,
    }),
    TableRow,
    TableHeader,
    TableCell,
  ];
}

export function normalizeAuthorTableAttributes(nodeType, attributes) {
  if (!new Set(["tableCell", "tableHeader"]).has(nodeType)) {
    return attributes;
  }
  if (!attributes || typeof attributes !== "object" || Array.isArray(attributes)) {
    return attributes;
  }
  const names = Object.keys(attributes);
  const onlyDefaults = names.every(
    (name) =>
      Object.hasOwn(CELL_DEFAULTS, name) &&
      Object.is(attributes[name], CELL_DEFAULTS[name]),
  );
  return onlyDefaults ? null : attributes;
}

function clamp(value, minimum, maximum) {
  if (maximum < minimum) return minimum;
  return Math.min(Math.max(value, minimum), maximum);
}

export function tableToolbarPosition({
  tableLeft,
  tableRight,
  tableTop,
  tableBottom,
  toolbarWidth,
  toolbarHeight,
  viewportLeft,
  viewportTop,
  viewportWidth,
  viewportHeight,
  clippingTop,
  clippingBottom,
}) {
  const safeLeft = viewportLeft + VIEWPORT_GUTTER;
  const safeRight = viewportLeft + viewportWidth - VIEWPORT_GUTTER;
  const visibleTableLeft = clamp(tableLeft, safeLeft, safeRight);
  const visibleTableRight = clamp(tableRight, safeLeft, safeRight);
  const minimumCenter = safeLeft + toolbarWidth / 2;
  const maximumCenter = safeRight - toolbarWidth / 2;
  const left = clamp(
    (visibleTableLeft + visibleTableRight) / 2,
    minimumCenter,
    maximumCenter,
  );
  const safeTop = Math.max(viewportTop, clippingTop) + VIEWPORT_GUTTER;
  const safeBottom = Math.min(
    viewportTop + viewportHeight,
    clippingBottom,
  ) - VIEWPORT_GUTTER;
  const above = tableTop - toolbarHeight - TOOLBAR_GAP;
  if (above >= safeTop) {
    return { left, top: above, placement: "above" };
  }
  const inside = clamp(
    tableTop + VIEWPORT_GUTTER,
    safeTop,
    Math.max(safeTop, Math.min(tableBottom, safeBottom) - toolbarHeight),
  );
  return { left, top: inside, placement: "inside" };
}

function icon(name) {
  const element = document.createElement("i");
  element.dataset.lucide = name;
  element.setAttribute("aria-hidden", "true");
  return element;
}

function commandButton(command, { menu = false, danger = false } = {}) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = menu
    ? "author-table-toolbar__menu-command"
    : "author-table-toolbar__command";
  button.dataset.editorTableCommand = command.id;
  button.setAttribute("aria-label", command.label);
  button.title = command.label;
  if (menu) button.setAttribute("role", "menuitem");
  if (danger) button.dataset.danger = "";
  button.append(icon(command.icon));
  if (menu) {
    const label = document.createElement("span");
    label.textContent = command.label;
    button.append(label);
  }
  return button;
}

function commandMenu({ label, iconName, commands, kind }) {
  const details = document.createElement("details");
  details.className = "author-table-toolbar__disclosure";
  details.dataset.tableMenu = kind;
  const summary = document.createElement("summary");
  summary.setAttribute("aria-label", label);
  summary.setAttribute("aria-haspopup", "menu");
  summary.setAttribute("aria-expanded", "false");
  summary.title = label;
  summary.append(icon(iconName));
  const menu = document.createElement("div");
  menu.className = "author-table-toolbar__menu";
  menu.setAttribute("role", "menu");
  menu.setAttribute("aria-label", label);
  commands.forEach((command) => {
    menu.append(
      commandButton(command, {
        menu: true,
        danger: command.id.startsWith("delete-"),
      }),
    );
  });
  details.append(summary, menu);
  details.addEventListener("toggle", () => {
    summary.setAttribute("aria-expanded", String(details.open));
  });
  return details;
}

function renderToolbar() {
  const commands = editorCommandsForSurface("table");
  const byId = new Map(commands.map((command) => [command.id, command]));
  const toolbar = document.createElement("div");
  toolbar.className = "author-table-toolbar";
  toolbar.dataset.editorTableToolbar = "";
  toolbar.setAttribute("role", "toolbar");
  toolbar.setAttribute("aria-label", "表格编辑");
  toolbar.hidden = true;
  toolbar.append(
    commandButton(byId.get("toggle-table-header")),
    commandMenu({
      label: "行操作",
      iconName: "rows-3",
      kind: "row",
      commands: [
        byId.get("add-table-row-before"),
        byId.get("add-table-row-after"),
        byId.get("delete-table-row"),
      ],
    }),
    commandMenu({
      label: "列操作",
      iconName: "columns-3",
      kind: "column",
      commands: [
        byId.get("add-table-column-before"),
        byId.get("add-table-column-after"),
        byId.get("delete-table-column"),
      ],
    }),
    commandButton(byId.get("delete-table"), { danger: true }),
  );
  createIcons({ attrs: { "stroke-width": 1.8 }, icons: ICONS, root: toolbar });
  return toolbar;
}

function currentTableElement(editor) {
  if (!editor?.isActive?.("table")) return null;
  let node = editor.view?.domAtPos?.(editor.state.selection.from)?.node;
  if (node?.nodeType === Node.TEXT_NODE) node = node.parentElement;
  const ancestor = node instanceof Element ? node.closest("table") : null;
  if (ancestor) return ancestor;
  const selected = editor.view?.nodeDOM?.(editor.state.selection.from);
  if (!(selected instanceof Element)) return null;
  return selected.matches("table") ? selected : selected.querySelector("table");
}

function closeMenus(toolbar, except = null) {
  toolbar
    .querySelectorAll(".author-table-toolbar__disclosure[open]")
    .forEach((details) => {
      if (details !== except) details.open = false;
    });
}

function menuButtons(details) {
  return Array.from(
    details.querySelectorAll(".author-table-toolbar__menu-command:not(:disabled)"),
  );
}

export function initializeEditorTableToolbar({ root, editor }) {
  const mount = root.querySelector("[data-tiptap-editor]");
  if (!(mount instanceof HTMLElement)) return null;
  const toolbar = renderToolbar();
  mount.before(toolbar);
  let frame = null;
  let dismissed = false;

  const updateStates = () => {
    toolbar.querySelectorAll("[data-editor-table-command]").forEach((button) => {
      const state = editorCommandState(editor, button.dataset.editorTableCommand);
      button.disabled = state.disabled;
      if (button.dataset.editorTableCommand === "toggle-table-header") {
        button.setAttribute("aria-pressed", String(state.active));
      }
    });
  };

  const position = () => {
    frame = null;
    const table = currentTableElement(editor);
    if (!table || dismissed) {
      toolbar.hidden = true;
      closeMenus(toolbar);
      return;
    }
    const tableSurface = table.closest(".tableWrapper") || table;
    const tableRect = tableSurface.getBoundingClientRect();
    const clippingRect = mount.getBoundingClientRect();
    const viewport = window.visualViewport;
    toolbar.hidden = false;
    updateStates();
    const placement = tableToolbarPosition({
      tableLeft: tableRect.left,
      tableRight: tableRect.right,
      tableTop: tableRect.top,
      tableBottom: tableRect.bottom,
      toolbarWidth: toolbar.offsetWidth,
      toolbarHeight: toolbar.offsetHeight,
      viewportLeft: viewport?.offsetLeft || 0,
      viewportTop: viewport?.offsetTop || 0,
      viewportWidth: viewport?.width || window.innerWidth,
      viewportHeight: viewport?.height || window.innerHeight,
      clippingTop: clippingRect.top,
      clippingBottom: clippingRect.bottom,
    });
    toolbar.style.left = `${placement.left}px`;
    toolbar.style.top = `${placement.top}px`;
    toolbar.dataset.placement = placement.placement;
  };

  const schedule = () => {
    if (frame !== null) return;
    frame = window.requestAnimationFrame(position);
  };

  const resetAndSchedule = () => {
    dismissed = false;
    schedule();
  };

  const activate = (event) => {
    const button = event.target.closest("[data-editor-table-command]");
    if (!(button instanceof HTMLButtonElement) || !toolbar.contains(button)) return;
    event.preventDefault();
    const ran = runEditorCommand(editor, button.dataset.editorTableCommand, {
      trigger: button,
    });
    if (!ran) return;
    closeMenus(toolbar);
    schedule();
  };

  const handleKeys = (event) => {
    const details = event.target.closest(".author-table-toolbar__disclosure");
    if (event.key === "Escape") {
      event.preventDefault();
      if (details?.open) {
        details.open = false;
        details.querySelector("summary")?.focus();
        return;
      }
      dismissed = true;
      toolbar.hidden = true;
      editor.commands.focus();
      return;
    }
    if (!(details instanceof HTMLDetailsElement)) return;
    const summary = details.querySelector("summary");
    const buttons = menuButtons(details);
    if (event.target === summary && ["ArrowDown", "ArrowUp"].includes(event.key)) {
      event.preventDefault();
      closeMenus(toolbar, details);
      details.open = true;
      (event.key === "ArrowDown" ? buttons[0] : buttons.at(-1))?.focus();
      return;
    }
    const index = buttons.indexOf(event.target);
    if (index < 0) return;
    const targets = {
      ArrowDown: buttons[(index + 1) % buttons.length],
      ArrowUp: buttons[(index - 1 + buttons.length) % buttons.length],
      Home: buttons[0],
      End: buttons.at(-1),
    };
    const target = targets[event.key];
    if (target) {
      event.preventDefault();
      target.focus();
    }
  };

  const handleToggle = (event) => {
    if (!(event.target instanceof HTMLDetailsElement) || !event.target.open) return;
    closeMenus(toolbar, event.target);
  };

  const handleOutside = (event) => {
    if (!toolbar.contains(event.target)) closeMenus(toolbar);
  };

  toolbar.addEventListener("click", activate);
  toolbar.addEventListener("keydown", handleKeys);
  toolbar.addEventListener("toggle", handleToggle, true);
  document.addEventListener("pointerdown", handleOutside);
  window.addEventListener("resize", schedule);
  window.addEventListener("scroll", schedule, true);
  window.visualViewport?.addEventListener("resize", schedule);
  window.visualViewport?.addEventListener("scroll", schedule);
  editor.on("selectionUpdate", resetAndSchedule);
  editor.on("update", schedule);
  schedule();

  return {
    update: schedule,
    dispose() {
      if (frame !== null) window.cancelAnimationFrame(frame);
      toolbar.removeEventListener("click", activate);
      toolbar.removeEventListener("keydown", handleKeys);
      toolbar.removeEventListener("toggle", handleToggle, true);
      document.removeEventListener("pointerdown", handleOutside);
      window.removeEventListener("resize", schedule);
      window.removeEventListener("scroll", schedule, true);
      window.visualViewport?.removeEventListener("resize", schedule);
      window.visualViewport?.removeEventListener("scroll", schedule);
      editor.off("selectionUpdate", resetAndSchedule);
      editor.off("update", schedule);
      toolbar.remove();
    },
  };
}
