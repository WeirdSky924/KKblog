import { Extension } from "@tiptap/core";
import { TaskItem, TaskList } from "@tiptap/extension-list";
import StarterKit from "@tiptap/starter-kit";

import { isolateNextEditorInputHistory } from "./editor-history.js";

export const AUTHOR_TRAILING_NODE_EXCLUSIONS = Object.freeze([
  "heading",
  "blockquote",
  "bulletList",
  "orderedList",
  "taskList",
  "callout",
  "codeBlock",
]);

const AuthorKeyboardShortcuts = Extension.create({
  name: "authorKeyboardShortcuts",
  priority: 1100,

  addOptions() {
    return {
      openLink: null,
    };
  },

  addKeyboardShortcuts() {
    return {
      Enter: () => isolateNextEditorInputHistory(this.editor),
      Backspace: () => isolateNextEditorInputHistory(this.editor),
      "Mod-k": () => {
        if (typeof this.options.openLink !== "function") return false;
        this.options.openLink({ editor: this.editor });
        return true;
      },
    };
  },
});

export function createAuthorInputExtensions({ openLink }) {
  return [
    TaskList.configure({}),
    TaskItem.configure({
      nested: true,
      a11y: {
        checkboxLabel: (_node, checked) =>
          checked ? "取消任务完成状态" : "标记任务为已完成",
      },
    }),
    AuthorKeyboardShortcuts.configure({ openLink }),
  ];
}

export function createAuthorStarterKit() {
  return StarterKit.configure({
    link: false,
    codeBlock: false,
    heading: false,
    trailingNode: { notAfter: [...AUTHOR_TRAILING_NODE_EXCLUSIONS] },
  });
}
