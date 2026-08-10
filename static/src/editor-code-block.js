import CodeBlock from "@tiptap/extension-code-block";
import { mergeAttributes } from "@tiptap/core";
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
