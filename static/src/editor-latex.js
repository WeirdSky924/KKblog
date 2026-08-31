import { Node as TipTapNode } from "@tiptap/core";
import katex from "katex";
import { X, createIcons } from "lucide";

import { dispatchIsolatedEditorTransaction } from "./editor-history.js";

const MAX_SOURCE_BYTES = 16 * 1024;
const MACRO_DEFINITION = /\\(?:newcommand|renewcommand|providecommand|def|gdef|xdef|edef|let|DeclareMathOperator|newenvironment|renewenvironment)\b/i;

function fallbackSource(source) {
  return `$$\n${source}\n$$`;
}

export function normalizeAuthorLatexSource(value) {
  if (typeof value !== "string") return "";
  if (new TextEncoder().encode(value).byteLength > MAX_SOURCE_BYTES) return "";
  if ([...value].some((character) => {
    const code = character.codePointAt(0);
    return code < 32 && ![9, 10, 13].includes(code);
  })) return "";
  return value.trim();
}

export function normalizeAuthorLatexAttributes(attributes) {
  const formula = normalizeAuthorLatexSource(attributes?.formula);
  return { formula };
}

function formulaCanRender(source) {
  return Boolean(source) && !MACRO_DEFINITION.test(source);
}

export function renderLatexElement(element, source) {
  if (!(element instanceof HTMLElement)) return false;
  const formula = normalizeAuthorLatexSource(source);
  element.dataset.kajLatex = "true";
  element.dataset.kajLatexSource = formula;
  element.replaceChildren();
  if (!formulaCanRender(formula)) {
    element.textContent = fallbackSource(formula);
    element.dataset.kajLatexError = "true";
    return false;
  }
  try {
    katex.render(formula, element, {
      displayMode: true,
      throwOnError: true,
      trust: false,
      strict: "error",
      output: "htmlAndMathml",
    });
    delete element.dataset.kajLatexError;
    return true;
  } catch {
    element.textContent = fallbackSource(formula);
    element.dataset.kajLatexError = "true";
    return false;
  }
}

export function initializeLatexRenderer(root = document) {
  root.querySelectorAll?.("[data-kaj-latex]").forEach((element) => {
    if (element instanceof HTMLElement) {
      renderLatexElement(element, element.dataset.kajLatexSource || element.textContent || "");
    }
  });
}

function iconButton(label) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "icon-button author-latex-dialog__close";
  button.setAttribute("aria-label", label);
  button.title = label;
  const icon = document.createElement("i");
  icon.dataset.lucide = "x";
  button.append(icon);
  return button;
}

function field(labelText, control) {
  const label = document.createElement("label");
  label.className = "author-latex-dialog__field";
  const labelTextNode = document.createElement("span");
  labelTextNode.textContent = labelText;
  label.append(labelTextNode, control);
  return label;
}

function restoreBookmark(editor, bookmark) {
  if (!editor || !bookmark) return;
  try {
    editor.view.dispatch(
      editor.state.tr
        .setSelection(bookmark.resolve(editor.state.doc))
        .setMeta("addToHistory", false),
    );
  } catch {
    // Keep the editor's current valid selection after a concurrent update.
  }
}

const AuthorLatex = TipTapNode.create({
  name: "latexBlock",
  group: "block",
  atom: true,
  draggable: true,
  selectable: true,
  addOptions() {
    return { openDialog: null };
  },
  addAttributes() {
    return {
      formula: {
        default: "",
        parseHTML: (element) => element.getAttribute("data-author-latex") || "",
      },
    };
  },
  parseHTML() {
    return [{ tag: "div[data-author-latex]" }];
  },
  renderHTML({ HTMLAttributes }) {
    const formula = normalizeAuthorLatexSource(HTMLAttributes.formula);
    return ["div", { "data-author-latex": formula }, fallbackSource(formula)];
  },
  addNodeView() {
    return ({ node, editor, getPos }) => {
      let currentNode = node;
      const dom = document.createElement("div");
      dom.className = "author-latex-block";
      dom.contentEditable = "false";
      const open = () => {
        const position = getPos();
        if (Number.isInteger(position)) this.options.openDialog?.({ trigger: dom, position });
      };
      dom.addEventListener("click", open);
      renderLatexElement(dom, node.attrs.formula);
      return {
        dom,
        update(nextNode) {
          if (nextNode.type !== currentNode.type) return false;
          currentNode = nextNode;
          renderLatexElement(dom, nextNode.attrs.formula);
          return true;
        },
        selectNode: () => dom.setAttribute("data-selected", "true"),
        deselectNode: () => dom.removeAttribute("data-selected"),
        stopEvent: (event) => event.type === "click",
        ignoreMutation: () => true,
        destroy: () => dom.removeEventListener("click", open),
      };
    };
  },
});

export function createAuthorLatexExtension(options = {}) {
  return AuthorLatex.configure(options);
}

export function initializeEditorLatexDialog({ root, editor = null, source = null }) {
  const host = root.closest("#author-editor-workspace") || document.body;
  const dialog = document.createElement("dialog");
  dialog.className = "author-latex-dialog";
  dialog.setAttribute("aria-labelledby", "author-latex-dialog-title");
  const form = document.createElement("form");
  form.method = "dialog";
  const header = document.createElement("header");
  const title = document.createElement("h3");
  title.id = "author-latex-dialog-title";
  title.textContent = "插入块级 LaTeX";
  const closeButton = iconButton("关闭 LaTeX 设置");
  header.append(title, closeButton);
  const input = document.createElement("textarea");
  input.rows = 7;
  input.required = true;
  input.placeholder = "\\int_0^1 x^2 \\,dx";
  input.setAttribute("aria-label", "LaTeX 公式源码");
  const preview = document.createElement("div");
  preview.className = "author-latex-dialog__preview";
  preview.setAttribute("aria-live", "polite");
  const error = document.createElement("p");
  error.className = "author-latex-dialog__error";
  error.setAttribute("role", "alert");
  error.hidden = true;
  const actions = document.createElement("div");
  actions.className = "author-latex-dialog__actions";
  const cancel = document.createElement("button");
  cancel.type = "button";
  cancel.className = "button button--secondary";
  cancel.textContent = "取消";
  const apply = document.createElement("button");
  apply.type = "submit";
  apply.className = "button button--primary";
  apply.textContent = "插入公式";
  actions.append(cancel, apply);
  form.append(header, field("公式源码（不含 $$ 分隔线）", input), preview, error, actions);
  dialog.append(form);
  host.append(dialog);
  createIcons({ root: dialog, icons: { X }, attrs: { "aria-hidden": "true", focusable: "false" } });

  let returnFocus = null;
  let bookmark = null;
  let editingPosition = null;
  let markdownRange = null;
  let restoreOnClose = false;
  const clearError = () => { error.hidden = true; error.textContent = ""; };
  const showError = (message) => { error.hidden = false; error.textContent = message; input.focus(); };
  const updatePreview = () => {
    const formula = normalizeAuthorLatexSource(input.value);
    renderLatexElement(preview, formula);
    apply.disabled = !formula;
    if (input.value && !formula) showError("公式不能为空，且不能超过 16 KiB 或包含控制字符。");
    else clearError();
  };
  const close = () => { if (dialog.open) dialog.close(); };
  const open = ({ trigger = null, position = null } = {}) => {
    if (!editor) return false;
    const node = Number.isInteger(position) ? editor.state.doc.nodeAt(position) : null;
    if (node && node.type.name !== "latexBlock") return false;
    returnFocus = trigger instanceof HTMLElement ? trigger : null;
    bookmark = editor.state.selection.getBookmark();
    editingPosition = node ? position : null;
    markdownRange = null;
    input.value = node?.attrs.formula || "";
    restoreOnClose = true;
    apply.textContent = node ? "保存公式" : "插入公式";
    clearError();
    if (!dialog.open) dialog.showModal();
    updatePreview();
    input.focus();
    return true;
  };
  const openMarkdown = (trigger) => {
    if (!(source instanceof HTMLTextAreaElement)) return false;
    returnFocus = trigger instanceof HTMLElement ? trigger : null;
    markdownRange = { start: source.selectionStart, end: source.selectionEnd };
    bookmark = null;
    editingPosition = null;
    input.value = "";
    restoreOnClose = true;
    apply.textContent = "插入公式";
    clearError();
    if (!dialog.open) dialog.showModal();
    updatePreview();
    input.focus();
    return true;
  };
  input.addEventListener("input", updatePreview);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const formula = normalizeAuthorLatexSource(input.value);
    if (!formula) { showError("请输入公式内容。"); return; }
    if (editor) {
      let transaction = editor.state.tr;
      if (Number.isInteger(editingPosition)) {
        const node = editor.state.doc.nodeAt(editingPosition);
        if (node?.type.name !== "latexBlock") { showError("公式位置已变化，请关闭后重试。"); return; }
        transaction = transaction.setNodeMarkup(editingPosition, undefined, { formula });
      } else {
        restoreBookmark(editor, bookmark);
        const node = editor.state.schema.nodes.latexBlock.create({ formula });
        transaction = transaction.replaceSelectionWith(node);
      }
      restoreOnClose = false;
      dispatchIsolatedEditorTransaction(editor, transaction, { focus: true });
    } else if (source instanceof HTMLTextAreaElement) {
      const range = markdownRange || { start: source.selectionStart, end: source.selectionEnd };
      source.focus();
      const insertion = `${range.start > 0 && source.value[range.start - 1] !== "\n" ? "\n" : ""}${fallbackSource(formula)}${range.end < source.value.length && source.value[range.end] !== "\n" ? "\n" : ""}`;
      source.setRangeText(insertion, range.start, range.end, "end");
      source.dispatchEvent(new Event("input", { bubbles: true }));
      restoreOnClose = false;
    }
    close();
  });
  closeButton.addEventListener("click", close);
  cancel.addEventListener("click", close);
  dialog.addEventListener("cancel", (event) => { event.preventDefault(); close(); });
  dialog.addEventListener("click", (event) => { if (event.target === dialog) close(); });
  dialog.addEventListener("close", () => {
    if (restoreOnClose && editor) restoreBookmark(editor, bookmark);
    restoreOnClose = false;
    bookmark = null;
    markdownRange = null;
    const target = returnFocus;
    returnFocus = null;
    requestAnimationFrame(() => target?.isConnected && target.focus({ preventScroll: true }));
  });
  return { open, openMarkdown, dispose: () => { if (dialog.open) dialog.close(); dialog.remove(); } };
}
