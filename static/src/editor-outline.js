import Heading from "@tiptap/extension-heading";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { ChevronLeft, ListTree, createIcons } from "lucide";

export const AUTHOR_HEADING_ANCHOR_PATTERN =
  /^kaj-h-[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

const headingAnchorPluginKey = new PluginKey("authorHeadingAnchors");

function normalizedHeadingAnchor(value) {
  return typeof value === "string" && AUTHOR_HEADING_ANCHOR_PATTERN.test(value)
    ? value
    : null;
}

function createHeadingAnchor() {
  return `kaj-h-${crypto.randomUUID()}`;
}

function uniqueHeadingAnchor(seen, createAnchor = createHeadingAnchor) {
  for (let attempt = 0; attempt < 32; attempt += 1) {
    const candidate = normalizedHeadingAnchor(createAnchor());
    if (candidate && !seen.has(candidate)) return candidate;
  }
  throw new Error("Unable to create a unique heading anchor");
}

function normalizedHeadingText(value) {
  const parts = [];
  const visit = (node) => {
    if (!node || typeof node !== "object") return;
    if (node.type === "text" && typeof node.text === "string") {
      parts.push(node.text);
    } else if (node.type === "hardBreak") {
      parts.push(" ");
    }
    if (Array.isArray(node.content)) node.content.forEach(visit);
  };
  visit(value);
  return parts.join("").replaceAll(/\s+/g, " ").trim();
}

export function normalizeHeadingDocument(document, createAnchor = createHeadingAnchor) {
  if (!document || typeof document !== "object") return document;
  const normalized = structuredClone(document);
  const seen = new Set();
  const visit = (node) => {
    if (!node || typeof node !== "object") return;
    if (node.type === "heading") {
      const attrs = node.attrs && typeof node.attrs === "object" ? node.attrs : {};
      let anchor = normalizedHeadingAnchor(attrs.anchor);
      if (!anchor || seen.has(anchor)) anchor = uniqueHeadingAnchor(seen, createAnchor);
      seen.add(anchor);
      node.attrs = { ...attrs, anchor };
    }
    if (Array.isArray(node.content)) node.content.forEach(visit);
  };
  visit(normalized);
  return normalized;
}

export function outlineFromTiptapDocument(document) {
  const items = [];
  const visit = (node) => {
    if (!node || typeof node !== "object") return;
    if (node.type === "heading") {
      const anchor = normalizedHeadingAnchor(node.attrs?.anchor);
      const level = Number(node.attrs?.level);
      if (anchor && Number.isInteger(level) && level >= 1 && level <= 6) {
        items.push({
          anchor,
          level,
          label: normalizedHeadingText(node) || "未命名标题",
        });
      }
    }
    if (Array.isArray(node.content)) node.content.forEach(visit);
  };
  visit(document);
  return items;
}

function headingAnchorPlugin() {
  return new Plugin({
    key: headingAnchorPluginKey,
    appendTransaction(transactions, _oldState, newState) {
      if (!transactions.some((transaction) => transaction.docChanged)) return null;
      const seen = new Set();
      const transaction = newState.tr;
      let changed = false;
      newState.doc.descendants((node, position) => {
        if (node.type.name !== "heading") return;
        let anchor = normalizedHeadingAnchor(node.attrs.anchor);
        if (!anchor || seen.has(anchor)) anchor = uniqueHeadingAnchor(seen);
        seen.add(anchor);
        if (anchor === node.attrs.anchor) return;
        transaction.setNodeMarkup(position, undefined, { ...node.attrs, anchor });
        changed = true;
      });
      return changed
        ? transaction.setMeta("authorHeadingAnchorNormalization", true)
        : null;
    },
  });
}

export function createAuthorHeadingExtension() {
  return Heading.extend({
    addAttributes() {
      return {
        ...(this.parent?.() || {}),
        anchor: {
          default: null,
          parseHTML: (element) => normalizedHeadingAnchor(element.getAttribute("id")),
          renderHTML: ({ anchor }) => {
            const normalized = normalizedHeadingAnchor(anchor);
            return normalized ? { id: normalized } : {};
          },
        },
      };
    },

    addProseMirrorPlugins() {
      return [...(this.parent?.() || []), headingAnchorPlugin()];
    },
  }).configure({ levels: [1, 2, 3, 4, 5, 6] });
}

function editorOutline(editor) {
  const items = [];
  editor.state.doc.descendants((node, position) => {
    if (node.type.name !== "heading") return;
    const anchor = normalizedHeadingAnchor(node.attrs.anchor);
    if (!anchor) return;
    items.push({
      anchor,
      level: node.attrs.level,
      label: node.textContent.replaceAll(/\s+/g, " ").trim() || "未命名标题",
      position,
    });
  });
  return items;
}

function scrollHeadingWithinEditor(editor, anchor) {
  const target = editor.view.dom.querySelector(`#${CSS.escape(anchor)}`);
  const viewport = editor.view.dom.closest(".author-tiptap");
  if (!(target instanceof HTMLElement) || !(viewport instanceof HTMLElement)) return;
  const viewportRect = viewport.getBoundingClientRect();
  const targetRect = target.getBoundingClientRect();
  const targetTop = viewport.scrollTop + targetRect.top - viewportRect.top;
  const centered = targetTop - (viewport.clientHeight - targetRect.height) / 2;
  const maximum = Math.max(viewport.scrollHeight - viewport.clientHeight, 0);
  viewport.scrollTop = Math.min(Math.max(centered, 0), maximum);
}

function element(tagName, { className = "", text = "", attributes = {} } = {}) {
  const node = document.createElement(tagName);
  if (className) node.className = className;
  if (text) node.textContent = text;
  Object.entries(attributes).forEach(([name, value]) => node.setAttribute(name, value));
  return node;
}

export function initializeEditorOutline({ root, editor }) {
  const host = root.querySelector("[data-editor-outline-host]");
  if (!(host instanceof HTMLElement) || !editor) return null;
  const navigation = element("nav", {
    className: "author-editor-outline",
    attributes: { "aria-label": "文章大纲" },
  });
  const details = element("details", { className: "author-editor-outline__details" });
  const summary = element("summary", { className: "author-editor-outline__summary" });
  const chevron = element("i", { attributes: { "data-lucide": "chevron-left" } });
  const panel = element("div", { className: "author-editor-outline__panel" });
  const header = element("header", { className: "author-editor-outline__header" });
  const icon = element("i", { attributes: { "data-lucide": "list-tree" } });
  const title = element("span", { text: "文章大纲" });
  const count = element("small", { text: "0" });
  const list = element("ol", { className: "author-editor-outline__list" });
  summary.append(chevron);
  header.append(icon, title, count);
  panel.append(header, list);
  details.append(summary, panel);
  navigation.append(details);
  host.replaceChildren(navigation);
  createIcons({
    attrs: { "stroke-width": 1.8 },
    icons: { ChevronLeft, ListTree },
    root: navigation,
  });

  const workspace = host.closest(".author-tiptap-workspace");
  const desktop = window.matchMedia("(min-width: 897px)");
  let items = [];
  const updateLayoutState = () => {
    const collapsed = !details.open;
    if (workspace instanceof HTMLElement) {
      workspace.dataset.outlineCollapsed = String(collapsed);
    }
    const label = `${collapsed ? "展开" : "收起"}文章大纲，${items.length} 个标题`;
    summary.setAttribute("aria-label", label);
    summary.title = label;
  };
  const setResponsiveState = () => {
    details.open = desktop.matches;
    updateLayoutState();
  };
  setResponsiveState();
  desktop.addEventListener("change", setResponsiveState);
  details.addEventListener("toggle", updateLayoutState);

  const updateActive = () => {
    const selection = editor.state.selection.from;
    let active = null;
    items.forEach((item) => {
      if (item.position <= selection) active = item.anchor;
    });
    list.querySelectorAll("button").forEach((button) => {
      if (button.dataset.outlineAnchor === active) {
        button.setAttribute("aria-current", "location");
      } else {
        button.removeAttribute("aria-current");
      }
    });
  };
  const render = () => {
    items = editorOutline(editor);
    count.textContent = String(items.length);
    updateLayoutState();
    list.replaceChildren();
    if (!items.length) {
      list.append(
        element("li", {
          className: "author-editor-outline__empty",
          text: "正文中暂无标题",
        }),
      );
      return;
    }
    items.forEach((item) => {
      const row = element("li");
      const button = element("button", {
        text: item.label,
        attributes: {
          type: "button",
          title: item.label,
          "aria-label": `前往 ${item.label}`,
          "data-outline-anchor": item.anchor,
        },
      });
      button.style.setProperty("--outline-depth", String(item.level - 1));
      row.append(button);
      list.append(row);
    });
    updateActive();
  };
  const selectHeading = (event) => {
    const button = event.target.closest("[data-outline-anchor]");
    if (!(button instanceof HTMLButtonElement)) return;
    const item = items.find((candidate) => candidate.anchor === button.dataset.outlineAnchor);
    if (!item) return;
    editor.commands.setTextSelection(Math.min(item.position + 1, editor.state.doc.content.size));
    editor.view.focus();
    scrollHeadingWithinEditor(editor, item.anchor);
  };
  list.addEventListener("click", selectHeading);
  editor.on("update", render);
  editor.on("selectionUpdate", updateActive);
  render();

  return {
    render,
    updateActive,
    dispose() {
      editor.off("update", render);
      editor.off("selectionUpdate", updateActive);
      list.removeEventListener("click", selectHeading);
      desktop.removeEventListener("change", setResponsiveState);
      details.removeEventListener("toggle", updateLayoutState);
      navigation.remove();
    },
  };
}
