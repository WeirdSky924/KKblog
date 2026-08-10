import { Extension } from "@tiptap/core";
import { Markdown } from "@tiptap/markdown";
import { DOMParser as ProseMirrorDOMParser, Slice } from "@tiptap/pm/model";
import { Plugin } from "@tiptap/pm/state";

import { normalizeCodeLanguage } from "./editor-code-block.js";
import { validateAuthorEmbedUrl } from "./editor-embed.js";
import { AUTHOR_MEDIA_SOURCE, AUTHOR_IMAGE_WIDTHS } from "./editor-image.js";
import { validateEditorLinkHref } from "./editor-link-dialog.js";

const MARKDOWN_BLOCK = /(^|\n)[ \t]{0,3}(?:#{1,6}[ \t]+|>[ \t]+|(?:[-+*]|\d+[.)])[ \t]+|```|~~~|(?:-{3,}|\*{3,}|_{3,})[ \t]*(?:\n|$))/m;
const MARKDOWN_TASK = /(^|\n)[ \t]*[-+*][ \t]+\[[ xX]\][ \t]+/m;
const MARKDOWN_TABLE = /(^|\n)[^\n|]*\|[^\n]*\n[ \t]*\|?[ \t]*:?-{3,}/m;
const MARKDOWN_INLINE = /(?:\*\*[^*\n]+\*\*|__[^_\n]+__|~~[^~\n]+~~|`[^`\n]+`|\[[^\]\n]+\]\([^\s)]+(?:\s+['"][^\n]*['"])?\))/;
const RAW_HTML = /<\/?[A-Za-z][^>\n]*>/;
const CONTROL = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/;
const DROP_WITH_CONTENT = new Set([
  "base", "canvas", "embed", "form", "iframe", "link", "math", "meta",
  "noscript", "object", "script", "style", "svg", "template",
]);
const ALLOWED_TAGS = new Set([
  "a", "aside", "b", "blockquote", "br", "code", "del", "div", "em",
  "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i", "img", "li", "ol",
  "p", "pre", "s", "span", "strike", "strong", "table", "tbody", "td",
  "tfoot", "th", "thead", "tr", "u", "ul",
]);
const WORD_WRAPPERS = new Set(["div", "span"]);
const CALLOUT_KINDS = new Set(["info", "success", "warning"]);
const HTML_BLOCK_TAGS = new Set([
  "aside", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "ol",
  "p", "pre", "table", "ul",
]);

function hasMarkdownBlockSyntax(value) {
  return [MARKDOWN_BLOCK, MARKDOWN_TASK, MARKDOWN_TABLE].some((pattern) =>
    pattern.test(value),
  );
}

export function isAuthorMarkdownPaste(value) {
  if (typeof value !== "string" || !value.trim() || CONTROL.test(value)) return false;
  if (RAW_HTML.test(value)) return false;
  return hasMarkdownBlockSyntax(value) || MARKDOWN_INLINE.test(value);
}

export function normalizeAuthorMarkdownDocument(value) {
  if (Array.isArray(value)) {
    return value.map(normalizeAuthorMarkdownDocument).filter(Boolean);
  }
  if (!value || typeof value !== "object") return value;
  if (["attachment", "embed", "image"].includes(value.type)) return null;
  const normalized = {};
  Object.entries(value).forEach(([key, item]) => {
    if (key === "marks" && Array.isArray(item)) {
      const marks = item.flatMap((mark) => {
        if (mark?.type !== "link") return [normalizeAuthorMarkdownDocument(mark)];
        const href = mark.attrs?.href;
        const result = validateEditorLinkHref(href);
        if (!result.valid) return [];
        const attrs = { href: result.value };
        if (typeof mark.attrs?.title === "string" && mark.attrs.title) {
          attrs.title = mark.attrs.title;
        }
        return [{ type: "link", attrs }];
      });
      if (marks.length) normalized.marks = marks;
      return;
    }
    if (key === "attrs" && value.type === "codeBlock") {
      normalized.attrs = { language: normalizeCodeLanguage(item?.language) };
      return;
    }
    if (key === "attrs" && value.type === "heading") {
      normalized.attrs = { level: item?.level };
      return;
    }
    const projected = normalizeAuthorMarkdownDocument(item);
    if (projected !== null && projected !== undefined) normalized[key] = projected;
  });
  return normalized;
}

function unwrap(element) {
  element.replaceWith(...element.childNodes);
}

function replaceTag(element, name) {
  const replacement = element.ownerDocument.createElement(name);
  replacement.append(...element.childNodes);
  element.replaceWith(replacement);
  return replacement;
}

function keepAttributes(element, values) {
  Array.from(element.attributes).forEach((attribute) =>
    element.removeAttribute(attribute.name),
  );
  Object.entries(values).forEach(([name, value]) => {
    if (value !== null && value !== undefined && value !== "") {
      element.setAttribute(name, String(value));
    }
  });
}

function cleanElement(element, enabledEmbedSources, report) {
  let tag = element.tagName.toLowerCase();
  if (DROP_WITH_CONTENT.has(tag)) {
    element.remove();
    report.dangerous += 1;
    return;
  }
  if (!ALLOWED_TAGS.has(tag)) {
    unwrap(element);
    report.noise += 1;
    return;
  }
  if (WORD_WRAPPERS.has(tag)) {
    unwrap(element);
    report.noise += 1;
    return;
  }
  if (tag === "a") {
    const href = element.getAttribute("href") || "";
    const checked = validateEditorLinkHref(href);
    if (!checked.valid) {
      unwrap(element);
      report.dangerous += 1;
      return;
    }
    keepAttributes(element, {
      href: checked.value,
      title: element.getAttribute("title") || null,
    });
    return;
  }
  if (tag === "img") {
    const mediaId = element.getAttribute("data-author-media-id") || "";
    if (!AUTHOR_MEDIA_SOURCE.test(`media:${mediaId}`)) {
      const alt = element.getAttribute("alt") || "";
      element.replaceWith(element.ownerDocument.createTextNode(alt));
      report.media += 1;
      return;
    }
    const width = Number(element.getAttribute("data-width") || 100);
    keepAttributes(element, {
      "data-author-media-id": mediaId,
      "data-width": AUTHOR_IMAGE_WIDTHS.includes(width) ? width : 100,
      alt: element.getAttribute("alt") || null,
      title: element.getAttribute("title") || null,
    });
    return;
  }
  if (tag === "aside") {
    const callout = element.getAttribute("data-callout") || "";
    const attachmentId = element.getAttribute("data-author-attachment-id") || "";
    const embedSource = element.getAttribute("data-author-embed-source") || "";
    const embedUrl = element.getAttribute("data-author-embed-url") || "";
    if (CALLOUT_KINDS.has(callout)) {
      keepAttributes(element, { "data-callout": callout });
      return;
    }
    if (AUTHOR_MEDIA_SOURCE.test(`media:${attachmentId}`)) {
      keepAttributes(element, { "data-author-attachment-id": attachmentId });
      return;
    }
    const embed = validateAuthorEmbedUrl(embedSource, embedUrl, enabledEmbedSources);
    if (embed.valid) {
      keepAttributes(element, {
        "data-author-embed-source": embed.source,
        "data-author-embed-url": embed.url,
      });
      return;
    }
    element = replaceTag(element, "blockquote");
    tag = "blockquote";
    report.noise += 1;
  }
  if (tag === "ol") {
    const start = element.getAttribute("start") || "";
    keepAttributes(element, { start: /^[1-9]\d{0,8}$/.test(start) ? start : null });
    return;
  }
  if (tag === "ul") {
    keepAttributes(element, {
      "data-type": element.getAttribute("data-type") === "taskList" ? "taskList" : null,
    });
    return;
  }
  if (tag === "li") {
    const task = element.getAttribute("data-type") === "taskItem";
    keepAttributes(element, {
      "data-type": task ? "taskItem" : null,
      "data-checked": task && element.getAttribute("data-checked") === "true" ? "true" : null,
    });
    return;
  }
  if (tag === "code") {
    const language = normalizeCodeLanguage(element.getAttribute("data-language"));
    keepAttributes(element, { "data-language": language === "text" ? null : language });
    return;
  }
  keepAttributes(element, {});
}

export function sanitizeAuthorPasteHtml(html, { enabledEmbedSources = [] } = {}) {
  if (typeof html !== "string" || !html) {
    return { html: "", dangerous: 0, media: 0, noise: 0 };
  }
  const parsed = new DOMParser().parseFromString(html, "text/html");
  const report = { dangerous: 0, media: 0, noise: 0 };
  const comments = [];
  const walker = parsed.createTreeWalker(parsed.body, NodeFilter.SHOW_COMMENT);
  while (walker.nextNode()) comments.push(walker.currentNode);
  comments.forEach((comment) => comment.remove());
  report.noise += comments.length;
  Array.from(parsed.body.querySelectorAll("*")).reverse().forEach((element) =>
    cleanElement(element, enabledEmbedSources, report),
  );
  return { html: parsed.body.innerHTML, ...report };
}

const AuthorPasteContract = Extension.create({
  name: "authorPasteContract",
  priority: 1200,
  addOptions() {
    return { announce: null, enabledEmbedSources: [] };
  },
  addProseMirrorPlugins() {
    const announce = this.options.announce;
    const enabledEmbedSources = this.options.enabledEmbedSources;
    return [
      new Plugin({
        props: {
          transformPastedHTML: (html) => {
            const result = sanitizeAuthorPasteHtml(html, { enabledEmbedSources });
            if (result.dangerous || result.media) {
              announce?.("已移除不安全内容或未上传的外部图片。", "warning");
            }
            return result.html;
          },
        },
      }),
    ];
  },
});

export function createAuthorPasteExtensions(options = {}) {
  return [
    Markdown.configure({ markedOptions: { breaks: false, gfm: true } }),
    AuthorPasteContract.configure(options),
  ];
}

export function insertAuthorMarkdown(editor, source) {
  if (!editor?.markdown || !isAuthorMarkdownPaste(source)) return false;
  const document = normalizeAuthorMarkdownDocument(editor.markdown.parse(source));
  const parsed = editor.schema.nodeFromJSON(document);
  const before = editor.state.doc;
  const slice = hasMarkdownBlockSyntax(source)
    ? new Slice(parsed.content, 0, 0)
    : Slice.maxOpen(parsed.content);
  editor.view.dispatch(
    editor.state.tr.replaceSelection(slice).scrollIntoView(),
  );
  editor.view.focus();
  return !editor.state.doc.eq(before);
}

export function insertAuthorHtml(editor, html, { enabledEmbedSources = [] } = {}) {
  const sanitized = sanitizeAuthorPasteHtml(html, { enabledEmbedSources });
  const source = new DOMParser().parseFromString(sanitized.html, "text/html");
  const block = Array.from(source.body.children).some((element) =>
    HTML_BLOCK_TAGS.has(element.tagName.toLowerCase()),
  );
  const parsed = ProseMirrorDOMParser.fromSchema(editor.schema).parse(source.body);
  const before = editor.state.doc;
  const slice = block
    ? new Slice(parsed.content, 0, 0)
    : Slice.maxOpen(parsed.content);
  editor.view.dispatch(editor.state.tr.replaceSelection(slice).scrollIntoView());
  editor.view.focus();
  return { ...sanitized, inserted: !editor.state.doc.eq(before) };
}

function clipboardHasImage(transfer) {
  return Array.from(transfer?.items || []).some(
    (item) => item.kind === "file" && item.type.startsWith("image/"),
  );
}

export function initializeEditorPasteContract({
  editor,
  announce,
  enabledEmbedSources = [],
}) {
  const target = editor?.view?.dom;
  if (!(target instanceof HTMLElement)) return null;
  const paste = (event) => {
    if (event.defaultPrevented || clipboardHasImage(event.clipboardData)) return;
    const html = event.clipboardData?.getData("text/html")?.trim() || "";
    if (html) {
      try {
        const result = insertAuthorHtml(editor, html, { enabledEmbedSources });
        event.preventDefault();
        event.stopImmediatePropagation();
        if (result.dangerous || result.media) {
          announce?.("已移除不安全内容或未上传的外部图片。", "warning");
        }
      } catch {
        announce?.("富文本结构无法识别，已按安全文本粘贴。", "warning");
      }
      return;
    }
    const source = event.clipboardData?.getData("text/plain") || "";
    if (!isAuthorMarkdownPaste(source) || !editor.markdown) return;
    try {
      if (!insertAuthorMarkdown(editor, source)) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      announce?.("Markdown 已按富文本结构粘贴。", "success");
    } catch {
      announce?.("Markdown 结构无法识别，已按纯文本粘贴。", "warning");
    }
  };
  target.addEventListener("paste", paste, true);
  return {
    dispose() {
      target.removeEventListener("paste", paste, true);
    },
  };
}
