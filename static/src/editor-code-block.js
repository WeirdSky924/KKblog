import CodeBlock from "@tiptap/extension-code-block";
import { mergeAttributes } from "@tiptap/core";
import { Fragment } from "@tiptap/pm/model";
import { NodeSelection, TextSelection } from "@tiptap/pm/state";
import { Copy, createIcons } from "lucide";

import { dispatchIsolatedEditorTransaction } from "./editor-history.js";

export const AUTHOR_CODE_LANGUAGES = Object.freeze(
  [
    ["text", "纯文本"],
    ["bash", "Bash"],
    ["css", "CSS"],
    ["diff", "Diff"],
    ["html", "HTML"],
    ["javascript", "JavaScript"],
    ["json", "JSON"],
    ["markdown", "Markdown"],
    ["python", "Python"],
    ["sql", "SQL"],
    ["typescript", "TypeScript"],
    ["yaml", "YAML"],
  ].map(([value, label]) => Object.freeze({ value, label })),
);

const languageValues = new Set(
  AUTHOR_CODE_LANGUAGES.map((language) => language.value),
);

function selectedTextBlockRange(state) {
  const selection = state?.selection;
  if (!selection?.$from || !selection.$to) return null;
  const range = selection.$from.blockRange(selection.$to);
  if (!range || range.parent.type.name === "codeBlock") return null;
  const blocks = [];
  for (let index = range.startIndex; index < range.endIndex; index += 1) {
    const node = range.parent.child(index);
    if (!node.isTextblock) return null;
    blocks.push(node);
  }
  return blocks.length ? { range, blocks } : null;
}

function codeBlockSelection(state) {
  const selection = state?.selection;
  if (!selection?.$from || !selection?.$to) return null;
  if (
    selection instanceof NodeSelection &&
    selection.node?.type.name === "codeBlock"
  ) {
    return {
      node: selection.node,
      from: selection.from,
      to: selection.to,
      offset: 0,
    };
  }
  const { $from, $to } = selection;
  if ($from.parent.type.name !== "codeBlock" || $to.parent !== $from.parent) {
    return null;
  }
  const depth = $from.depth;
  const node = $from.node(depth);
  return {
    node,
    from: $from.before(depth),
    to: $from.after(depth),
    offset: $from.parentOffset,
  };
}

export function restoreCodeBlockAsParagraphs({ state, tr }) {
  const selected = codeBlockSelection(state);
  if (!selected) return null;

  const lines = selected.node.textContent.split(/\r?\n/);
  const paragraphType = state.schema.nodes.paragraph;
  if (!paragraphType) return false;
  const paragraphs = lines.map((line) =>
    paragraphType.create(null, line ? state.schema.text(line) : null),
  );
  const transaction = tr || state.tr;
  transaction.replaceWith(
    selected.from,
    selected.to,
    Fragment.from(paragraphs),
  );

  const beforeCursor = selected.node.textContent.slice(0, selected.offset);
  const lineIndex = Math.min(
    lines.length - 1,
    beforeCursor.split(/\r?\n/).length - 1,
  );
  const lineOffset = beforeCursor.length - beforeCursor.lastIndexOf("\n") - 1;
  let cursor = selected.from + 1;
  for (let index = 0; index < lineIndex; index += 1) {
    cursor += paragraphs[index].nodeSize;
  }
  cursor += Math.min(lineOffset, lines[lineIndex].length);
  transaction.setSelection(TextSelection.create(transaction.doc, cursor));
  return true;
}

export function mergeSelectedCodeBlocks({
  state,
  tr,
  attributes,
  defaultLanguage,
}) {
  const selected = selectedTextBlockRange(state);
  if (!selected || selected.blocks.length < 2) return null;

  // Selecting existing code blocks means "toggle off". For a mixed selection,
  // replace the complete block range so ProseMirror creates one code block.
  if (selected.blocks.every((node) => node.type.name === "codeBlock")) {
    return null;
  }
  const codeBlockType = state.schema.nodes.codeBlock;
  if (!codeBlockType || !selected.range.parent.canReplaceWith(
    selected.range.startIndex,
    selected.range.endIndex,
    codeBlockType,
  )) {
    return false;
  }
  const text = selected.blocks.map((node) => node.textContent).join("\n");
  const language = normalizeCodeLanguage(
    attributes?.language || defaultLanguage,
  );
  const codeBlock = codeBlockType.create(
    { language },
    text ? state.schema.text(text) : null,
  );
  (tr || state.tr).replaceWith(
    selected.range.start,
    selected.range.end,
    codeBlock,
  );
  return true;
}

export function normalizeCodeLanguage(value) {
  return languageValues.has(value) ? value : "text";
}

export async function copyCodeText(value, writeText) {
  if (typeof writeText !== "function") {
    throw new Error("clipboard unavailable");
  }
  await writeText(String(value ?? ""));
}

function announce(message, level) {
  document.dispatchEvent(
    new CustomEvent("kaj:feedback", {
      detail: {
        key: "code-block-copy",
        level,
        message,
        timeout: level === "success" ? 4200 : 6500,
      },
    }),
  );
}

function copyButton() {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "code-block-tools__copy";
  button.setAttribute("aria-label", "复制代码");
  button.title = "复制代码";
  const icon = document.createElement("i");
  icon.dataset.lucide = "copy";
  button.append(icon);
  createIcons({
    root: button,
    icons: { Copy },
    attrs: {
      "aria-hidden": "true",
      focusable: "false",
      width: "18",
      height: "18",
    },
  });
  return button;
}

async function copyFromCode(code, button) {
  if (button.disabled) return;
  button.disabled = true;
  try {
    await copyCodeText(
      code.textContent,
      navigator.clipboard?.writeText?.bind(navigator.clipboard),
    );
    button.dataset.copied = "";
    announce("代码已复制。", "success");
  } catch {
    announce("复制失败，请检查浏览器剪贴板权限。", "error");
  } finally {
    button.disabled = false;
  }
}

function languageSelect(value) {
  const select = document.createElement("select");
  select.className = "author-code-block__language";
  select.setAttribute("aria-label", "代码语言");
  AUTHOR_CODE_LANGUAGES.forEach((language) => {
    const option = document.createElement("option");
    option.value = language.value;
    option.textContent = language.label;
    select.append(option);
  });
  select.value = normalizeCodeLanguage(value);
  return select;
}

const AuthorCodeBlock = CodeBlock.extend({
  addCommands() {
    const parent = this.parent?.() || {};
    return {
      ...parent,
      toggleAuthorCodeBlock:
        (attributes) =>
        ({ state, tr, commands }) => {
          const restored = restoreCodeBlockAsParagraphs({ state, tr });
          if (restored !== null) return restored;
          const merged = mergeSelectedCodeBlocks({
            state,
            tr,
            attributes,
            defaultLanguage: this.options.defaultLanguage,
          });
          if (merged !== null) return merged;
          return commands.toggleCodeBlock(attributes);
        },
    };
  },

  addKeyboardShortcuts() {
    return {
      ...(this.parent?.() || {}),
      "Mod-Alt-c": () => this.editor.commands.toggleAuthorCodeBlock(),
    };
  },

  addAttributes() {
    return {
      language: {
        default: this.options.defaultLanguage,
        parseHTML: (element) =>
          normalizeCodeLanguage(
            element.firstElementChild?.getAttribute("data-language"),
          ),
        rendered: false,
      },
    };
  },

  renderHTML({ node, HTMLAttributes }) {
    const language = normalizeCodeLanguage(node.attrs.language);
    return [
      "pre",
      mergeAttributes(this.options.HTMLAttributes, HTMLAttributes),
      ["code", { "data-language": language }, 0],
    ];
  },

  addNodeView() {
    return ({ node, editor, getPos }) => {
      let currentNode = node;
      const dom = document.createElement("div");
      dom.className = "author-code-block";
      const toolbar = document.createElement("div");
      toolbar.className = "author-code-block__tools";
      toolbar.contentEditable = "false";
      const select = languageSelect(node.attrs.language);
      const copy = copyButton();
      toolbar.append(select, copy);
      const pre = document.createElement("pre");
      const code = document.createElement("code");
      code.dataset.language = normalizeCodeLanguage(node.attrs.language);
      pre.append(code);
      dom.append(toolbar, pre);

      const changeLanguage = () => {
        const position = getPos();
        if (!Number.isInteger(position)) return;
        const current = editor.state.doc.nodeAt(position);
        if (!current || current.type !== currentNode.type) return;
        const language = normalizeCodeLanguage(select.value);
        if (current.attrs.language === language) return;
        dispatchIsolatedEditorTransaction(
          editor,
          editor.state.tr.setNodeMarkup(position, undefined, {
            ...current.attrs,
            language,
          }),
        );
      };
      const copyCurrent = () => copyFromCode(code, copy);
      select.addEventListener("change", changeLanguage);
      copy.addEventListener("click", copyCurrent);

      return {
        dom,
        contentDOM: code,
        update(nextNode) {
          if (nextNode.type !== currentNode.type) return false;
          currentNode = nextNode;
          const language = normalizeCodeLanguage(nextNode.attrs.language);
          select.value = language;
          code.dataset.language = language;
          copy.removeAttribute("data-copied");
          return true;
        },
        stopEvent: (event) => toolbar.contains(event.target),
        ignoreMutation: (mutation) => toolbar.contains(mutation.target),
        destroy() {
          select.removeEventListener("change", changeLanguage);
          copy.removeEventListener("click", copyCurrent);
        },
      };
    };
  },
});

export function createAuthorCodeBlockExtension() {
  return AuthorCodeBlock.configure({
    defaultLanguage: "text",
    languageClassPrefix: null,
  });
}

export function initializeReadableCodeBlocks(root = document) {
  root.querySelectorAll?.(".article-prose pre > code").forEach((code) => {
    const pre = code.parentElement;
    if (!(pre instanceof HTMLElement) || pre.dataset.codeToolsBound === "true") {
      return;
    }
    pre.dataset.codeToolsBound = "true";
    const wrapper = document.createElement("div");
    wrapper.className = "article-code-block";
    const tools = document.createElement("div");
    tools.className = "article-code-block__tools";
    const language = document.createElement("span");
    language.textContent = AUTHOR_CODE_LANGUAGES.find(
      (item) => item.value === normalizeCodeLanguage(code.dataset.language),
    ).label;
    const copy = copyButton();
    copy.addEventListener("click", () => copyFromCode(code, copy));
    tools.append(language, copy);
    pre.parentElement?.insertBefore(wrapper, pre);
    wrapper.append(tools, pre);
  });
}
