import { Editor } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";

function toolbarButton(label, title, command) {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = label;
  button.title = title;
  button.setAttribute("aria-label", title);
  button.addEventListener("click", command);
  return button;
}

function initializeRichTextEditor(container, source) {
  const mount = document.createElement("div");
  mount.className = "site-static-editor__canvas";
  const toolbar = document.createElement("div");
  toolbar.className = "site-static-editor__toolbar";
  toolbar.setAttribute("role", "toolbar");
  toolbar.setAttribute("aria-label", "富文本格式");
  container.append(toolbar, mount);
  source.hidden = true;

  const editor = new Editor({
    element: mount,
    extensions: [StarterKit],
    content: source.value || "<p></p>",
    editorProps: {
      attributes: {
        class: "site-static-editor__content",
        "aria-label": "页面正文",
      },
    },
    onUpdate: ({ editor: activeEditor }) => {
      source.value = activeEditor.getText().trim() ? activeEditor.getHTML() : "";
    },
  });
  toolbar.append(
    toolbarButton("B", "粗体", () => editor.chain().focus().toggleBold().run()),
    toolbarButton("I", "斜体", () => editor.chain().focus().toggleItalic().run()),
    toolbarButton("H2", "二级标题", () =>
      editor.chain().focus().toggleHeading({ level: 2 }).run(),
    ),
    toolbarButton("•", "无序列表", () =>
      editor.chain().focus().toggleBulletList().run(),
    ),
    toolbarButton('"', "引用", () =>
      editor.chain().focus().toggleBlockquote().run(),
    ),
  );
  return () => {
    source.value = editor.getText().trim() ? editor.getHTML() : "";
    editor.destroy();
    toolbar.remove();
    mount.remove();
    source.hidden = false;
  };
}

export function initializeAdministrationSettings(root = document) {
  root.querySelectorAll?.("[data-static-editor]").forEach((container) => {
    if (!(container instanceof HTMLElement) || container.dataset.bound === "true") {
      return;
    }
    const form = container.closest("form");
    const source = container.querySelector("textarea");
    const format = form?.querySelector("select[name$='content_format']");
    if (!(source instanceof HTMLTextAreaElement) || !(format instanceof HTMLSelectElement)) {
      return;
    }
    container.dataset.bound = "true";
    let destroyEditor = null;
    const synchronize = () => {
      destroyEditor?.();
      destroyEditor = null;
      if (format.value === "RICH_TEXT") {
        destroyEditor = initializeRichTextEditor(container, source);
      }
    };
    format.addEventListener("change", synchronize);
    synchronize();
  });

  root.querySelectorAll?.("form[data-confirm-form]").forEach((form) => {
    if (!(form instanceof HTMLFormElement) || form.dataset.confirmBound === "true") {
      return;
    }
    form.dataset.confirmBound = "true";
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirmForm || "确认继续？")) {
        event.preventDefault();
      }
    });
  });
}
