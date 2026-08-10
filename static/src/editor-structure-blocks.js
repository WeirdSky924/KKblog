import { Node, mergeAttributes } from "@tiptap/core";

export const AUTHOR_CALLOUT_KINDS = Object.freeze([
  "info",
  "success",
  "warning",
]);

function safeCalloutKind(value) {
  return AUTHOR_CALLOUT_KINDS.includes(value) ? value : "info";
}

export const AuthorCallout = Node.create({
  name: "callout",
  group: "block",
  content: "block+",
  defining: true,

  addAttributes() {
    return { kind: { default: "info" } };
  },

  addCommands() {
    return {
      setCallout:
        (requestedKind) =>
        ({ editor, commands }) => {
          if (!AUTHOR_CALLOUT_KINDS.includes(requestedKind)) return false;
          if (!editor.isActive(this.name)) {
            return commands.wrapIn(this.name, { kind: requestedKind });
          }
          if (editor.isActive(this.name, { kind: requestedKind })) {
            return commands.lift(this.name);
          }
          return commands.updateAttributes(this.name, { kind: requestedKind });
        },
    };
  },

  parseHTML() {
    return [
      {
        tag: "aside[data-callout]",
        getAttrs: (element) => ({
          kind: safeCalloutKind(element.getAttribute("data-callout")),
        }),
      },
    ];
  },

  renderHTML({ HTMLAttributes }) {
    const kind = safeCalloutKind(HTMLAttributes.kind);
    const attributes = { ...HTMLAttributes };
    delete attributes.kind;
    return [
      "aside",
      mergeAttributes(attributes, { "data-callout": kind }),
      0,
    ];
  },
});

export function createAuthorStructureExtensions() {
  return [AuthorCallout];
}
