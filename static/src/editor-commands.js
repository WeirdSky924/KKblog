import {
  closeEditorHistory,
  isolateEditorTransaction,
} from "./editor-history.js";
import {
  authorTableCanAddColumn,
  authorTableCanAddRow,
} from "./editor-table-contract.js";

function selectedTable(editor) {
  const selection = editor?.state?.selection;
  if (!selection?.$from) return null;
  for (let depth = selection.$from.depth; depth >= 0; depth -= 1) {
    const node = selection.$from.node(depth);
    if (node.type.name === "table") return node;
  }
  return null;
}

function tableHasHeaderRow(editor) {
  const table = selectedTable(editor);
  const firstRow = table?.firstChild;
  if (!firstRow?.childCount) return false;
  let hasOnlyHeaders = true;
  firstRow.forEach((cell) => {
    if (cell.type.name !== "tableHeader") hasOnlyHeaders = false;
  });
  return hasOnlyHeaders;
}

function tableAllowsRowAddition(editor) {
  return editor.isActive("table") && authorTableCanAddRow(selectedTable(editor));
}

function tableAllowsColumnAddition(editor) {
  return editor.isActive("table") && authorTableCanAddColumn(selectedTable(editor));
}

const definitions = [
  {
    id: "paragraph",
    label: "正文",
    description: "继续书写普通正文",
    aliases: ["段落", "文本", "paragraph", "text"],
    icon: "pilcrow",
    group: "block",
    presentation: "block-type",
    toolbarPlacement: "block",
    compact: "primary",
    command: "setParagraph",
    active: { name: "paragraph" },
    shortcut: "Mod-Alt-0",
    surfaces: ["toolbar", "slash", "block"],
  },
  ...Array.from({ length: 6 }, (_, index) => {
    const level = index + 1;
    const chineseLevel = ["一", "二", "三", "四", "五", "六"][index];
    return {
      id: `heading-${level}`,
      label: `标题 ${level}`,
      description: `创建 ${level} 级章节标题`,
      aliases: [
        `标题${level}`,
        `${level}级标题`,
        `${chineseLevel}级标题`,
        `h${level}`,
        `heading ${level}`,
      ],
      icon: `heading-${level}`,
      group: "block",
      presentation: "block-type",
      toolbarPlacement: "block",
      compact: "primary",
      command: "toggleHeading",
      commandArgs: [{ level }],
      active: { name: "heading", attrs: { level } },
      shortcut: `Mod-Alt-${level}`,
      surfaces: ["toolbar", "slash", "block"],
    };
  }),
  {
    id: "bold",
    label: "粗体",
    icon: "bold",
    group: "text",
    toolbarPlacement: "primary",
    compact: "primary",
    command: "toggleBold",
    active: { name: "bold" },
    shortcut: "Mod-b",
    surfaces: ["toolbar", "bubble"],
  },
  {
    id: "italic",
    label: "斜体",
    icon: "italic",
    group: "text",
    toolbarPlacement: "primary",
    compact: "primary",
    command: "toggleItalic",
    active: { name: "italic" },
    shortcut: "Mod-i",
    surfaces: ["toolbar", "bubble"],
  },
  {
    id: "strike",
    label: "删除线",
    icon: "strikethrough",
    group: "text",
    toolbarPlacement: "overflow",
    compact: "overflow",
    command: "toggleStrike",
    active: { name: "strike" },
    shortcut: "Mod-Shift-s",
    surfaces: ["toolbar", "bubble"],
  },
  {
    id: "underline",
    label: "下划线",
    icon: "underline",
    group: "text",
    toolbarPlacement: "primary",
    compact: "overflow",
    command: "toggleUnderline",
    active: { name: "underline" },
    shortcut: "Mod-u",
    surfaces: ["toolbar", "bubble"],
  },
  {
    id: "inline-code",
    label: "行内代码",
    icon: "code",
    group: "text",
    toolbarPlacement: "primary",
    compact: "overflow",
    command: "toggleCode",
    active: { name: "code" },
    shortcut: "Mod-e",
    surfaces: ["toolbar", "bubble"],
  },
  {
    id: "link",
    label: "链接",
    icon: "link",
    group: "text",
    toolbarPlacement: "primary",
    compact: "overflow",
    action: "link-dialog",
    active: { name: "link" },
    shortcut: "Mod-k",
    surfaces: ["toolbar", "bubble"],
  },
  {
    id: "clear-format",
    label: "清除格式",
    icon: "remove-formatting",
    group: "text",
    toolbarPlacement: "overflow",
    compact: "overflow",
    steps: [{ command: "unsetAllMarks" }, { command: "clearNodes" }],
    active: null,
    shortcut: null,
    surfaces: ["toolbar", "bubble"],
  },
  {
    id: "bulletList",
    label: "无序列表",
    description: "创建项目符号列表",
    aliases: ["项目符号", "bullet", "unordered", "list"],
    icon: "list",
    group: "structure",
    toolbarPlacement: "primary",
    compact: "primary",
    command: "toggleBulletList",
    active: { name: "bulletList" },
    shortcut: "Mod-Shift-8",
    surfaces: ["toolbar", "slash", "block"],
  },
  {
    id: "orderedList",
    label: "有序列表",
    description: "创建带序号的项目列表",
    aliases: ["序号", "编号", "ordered", "numbered list"],
    icon: "list-ordered",
    group: "structure",
    toolbarPlacement: "primary",
    compact: "overflow",
    command: "toggleOrderedList",
    active: { name: "orderedList" },
    shortcut: "Mod-Shift-7",
    surfaces: ["toolbar", "slash", "block"],
  },
  {
    id: "blockquote",
    label: "引用",
    description: "突出展示引用内容",
    aliases: ["引文", "quote", "blockquote"],
    icon: "quote",
    group: "structure",
    toolbarPlacement: "overflow",
    compact: "overflow",
    command: "toggleBlockquote",
    active: { name: "blockquote" },
    shortcut: "Mod-Shift-b",
    surfaces: ["toolbar", "slash", "block"],
  },
  {
    id: "codeBlock",
    label: "代码块",
    description: "插入等宽代码段",
    aliases: ["代码", "code", "code block"],
    icon: "square-code",
    group: "structure",
    toolbarPlacement: "overflow",
    compact: "overflow",
    command: "toggleAuthorCodeBlock",
    active: { name: "codeBlock" },
    shortcut: "Mod-Alt-c",
    surfaces: ["toolbar", "slash", "block"],
  },
  {
    id: "taskList",
    label: "任务列表",
    description: "创建可以勾选的任务清单",
    aliases: ["待办", "清单", "任务", "todo", "task list"],
    icon: "list-checks",
    group: "structure",
    toolbarPlacement: "overflow",
    compact: "overflow",
    command: "toggleTaskList",
    active: { name: "taskList" },
    shortcut: null,
    surfaces: ["toolbar", "slash", "block"],
  },
  {
    id: "latex-block",
    label: "插入公式",
    description: "插入只占一整行的块级 LaTeX 公式",
    aliases: ["公式", "latex", "math", "数学"],
    icon: "sigma",
    group: "structure",
    toolbarPlacement: "primary",
    compact: "primary",
    action: "latex-dialog",
    actionRequiresSelection: false,
    active: { name: "latexBlock" },
    shortcut: null,
    surfaces: ["toolbar", "slash"],
  },
  ...[
    {
      kind: "info",
      label: "信息提示",
      description: "插入需要读者留意的信息",
      aliases: ["提示", "说明", "info", "callout"],
      icon: "info",
    },
    {
      kind: "success",
      label: "完成提示",
      description: "插入完成或确认信息",
      aliases: ["完成", "成功", "success", "callout"],
      icon: "circle-check",
    },
    {
      kind: "warning",
      label: "警告提示",
      description: "插入风险或注意事项",
      aliases: ["警告", "注意", "warning", "callout"],
      icon: "triangle-alert",
    },
  ].map((definition) => ({
    id: `callout-${definition.kind}`,
    label: definition.label,
    description: definition.description,
    aliases: definition.aliases,
    icon: definition.icon,
    group: "structure",
    toolbarPlacement: "overflow",
    compact: "overflow",
    command: "setCallout",
    commandArgs: [definition.kind],
    active: { name: "callout", attrs: { kind: definition.kind } },
    shortcut: null,
    surfaces: ["toolbar", "slash", "block"],
  })),
  {
    id: "horizontal-rule",
    label: "分隔线",
    description: "在上下内容之间添加分隔",
    aliases: ["横线", "分割线", "divider", "horizontal rule", "hr"],
    icon: "minus",
    group: "structure",
    toolbarPlacement: "overflow",
    compact: "overflow",
    command: "setHorizontalRule",
    active: { name: "horizontalRule" },
    shortcut: null,
    surfaces: ["toolbar", "slash", "block"],
  },
  {
    id: "insert-table",
    label: "插入表格",
    description: "插入三列三行的基础表格",
    aliases: ["表格", "table", "grid"],
    icon: "table-2",
    group: "structure",
    toolbarPlacement: "overflow",
    compact: "overflow",
    command: "insertTable",
    commandArgs: [{ rows: 3, cols: 3, withHeaderRow: true }],
    active: null,
    available: (editor) => !editor.isActive("table"),
    shortcut: null,
    surfaces: ["toolbar", "slash"],
  },
  {
    id: "toggle-table-header",
    label: "切换表头行",
    icon: "panel-top",
    group: "table",
    toolbarPlacement: "context",
    compact: "context",
    command: "toggleHeaderRow",
    active: tableHasHeaderRow,
    available: (editor) => editor.isActive("table"),
    shortcut: null,
    surfaces: ["table"],
  },
  {
    id: "add-table-row-before",
    label: "在上方插入行",
    icon: "arrow-up-to-line",
    group: "table",
    toolbarPlacement: "context",
    compact: "context",
    command: "addRowBefore",
    active: null,
    available: tableAllowsRowAddition,
    shortcut: null,
    surfaces: ["table"],
  },
  {
    id: "add-table-row-after",
    label: "在下方插入行",
    icon: "arrow-down-to-line",
    group: "table",
    toolbarPlacement: "context",
    compact: "context",
    command: "addRowAfter",
    active: null,
    available: tableAllowsRowAddition,
    shortcut: null,
    surfaces: ["table"],
  },
  {
    id: "delete-table-row",
    label: "删除当前行",
    icon: "rows-3",
    group: "table",
    toolbarPlacement: "context",
    compact: "context",
    command: "deleteRow",
    active: null,
    available: (editor) => editor.isActive("table"),
    shortcut: null,
    surfaces: ["table"],
  },
  {
    id: "add-table-column-before",
    label: "在左侧插入列",
    icon: "arrow-left-to-line",
    group: "table",
    toolbarPlacement: "context",
    compact: "context",
    command: "addColumnBefore",
    active: null,
    available: tableAllowsColumnAddition,
    shortcut: null,
    surfaces: ["table"],
  },
  {
    id: "add-table-column-after",
    label: "在右侧插入列",
    icon: "arrow-right-to-line",
    group: "table",
    toolbarPlacement: "context",
    compact: "context",
    command: "addColumnAfter",
    active: null,
    available: tableAllowsColumnAddition,
    shortcut: null,
    surfaces: ["table"],
  },
  {
    id: "delete-table-column",
    label: "删除当前列",
    icon: "columns-3",
    group: "table",
    toolbarPlacement: "context",
    compact: "context",
    command: "deleteColumn",
    active: null,
    available: (editor) => editor.isActive("table"),
    shortcut: null,
    surfaces: ["table"],
  },
  {
    id: "delete-table",
    label: "删除表格",
    icon: "trash-2",
    group: "table",
    toolbarPlacement: "context",
    compact: "context",
    command: "deleteTable",
    active: null,
    available: (editor) => editor.isActive("table"),
    shortcut: null,
    surfaces: ["table"],
  },
  {
    id: "hard-break",
    label: "硬换行",
    icon: "corner-down-left",
    group: "structure",
    toolbarPlacement: "overflow",
    compact: "overflow",
    command: "setHardBreak",
    active: null,
    shortcut: "Shift-Enter",
    surfaces: ["toolbar"],
  },
  {
    id: "embed",
    label: "嵌入内容",
    icon: "square-play",
    group: "structure",
    toolbarPlacement: "overflow",
    compact: "overflow",
    action: "embed-dialog",
    actionRequiresSelection: false,
    active: { name: "embed" },
    available: (editor) => Boolean(editor.storage?.embed?.enabledSources?.length),
    shortcut: null,
    surfaces: ["toolbar"],
  },
  {
    id: "undo",
    label: "撤销",
    icon: "undo-2",
    group: "history",
    toolbarPlacement: "primary",
    compact: "primary",
    command: "undo",
    active: null,
    shortcut: "Mod-z",
    surfaces: ["toolbar"],
  },
  {
    id: "redo",
    label: "重做",
    icon: "redo-2",
    group: "history",
    toolbarPlacement: "primary",
    compact: "primary",
    command: "redo",
    active: null,
    shortcut: "Mod-Shift-z",
    surfaces: ["toolbar"],
  },
];

function freezeSteps(definition) {
  if (definition.action) return Object.freeze([]);
  const source =
    definition.steps ||
    [{ command: definition.command, args: definition.commandArgs || [] }];
  return Object.freeze(
    source.map((step) =>
      Object.freeze({
        command: step.command,
        args: Object.freeze([...(step.args || [])]),
      }),
    ),
  );
}

export const EDITOR_COMMANDS = Object.freeze(
  definitions.map((definition) =>
    Object.freeze({
      ...definition,
      steps: freezeSteps(definition),
      permission: "edit",
      history:
        definition.history ||
        (["block", "structure", "table"].includes(definition.group) &&
        definition.id !== "hard-break"
          ? "isolated"
          : "default"),
      presentation: definition.presentation || "button",
      aliases: Object.freeze([...(definition.aliases || [])]),
      surfaces: Object.freeze([...definition.surfaces]),
    }),
  ),
);

const commandsById = new Map(EDITOR_COMMANDS.map((command) => [command.id, command]));

export function editorCommandsForSurface(surface) {
  return EDITOR_COMMANDS.filter((command) => command.surfaces.includes(surface));
}

function configuredChain(
  editor,
  command,
  {
    capability = false,
    isolateHistory = false,
    prepareChain = null,
    skipCommand = false,
  } = {},
) {
  if (!editor || !command || editor.isEditable === false) return null;
  if (
    typeof command.available === "function" &&
    !command.available(editor)
  ) {
    return null;
  }
  const owner = capability ? editor.can?.() : editor;
  let chain = owner?.chain?.().focus?.();
  if (!chain) return null;
  if (isolateHistory) {
    if (typeof chain.command !== "function") return null;
    chain = chain.command(({ tr }) => {
      isolateEditorTransaction(tr);
      return true;
    });
  }
  if (typeof prepareChain === "function") {
    chain = prepareChain(chain);
    if (!chain) return null;
  }
  if (skipCommand) return chain;
  for (const step of command.steps) {
    const method = chain[step.command];
    if (typeof method !== "function") return null;
    chain = method.apply(chain, step.args);
  }
  return chain;
}

function commandIsActive(editor, command) {
  if (typeof command.active === "function") return Boolean(command.active(editor));
  return command.active
    ? editor.isActive(command.active.name, command.active.attrs)
    : false;
}

export function editorCommandState(
  editor,
  commandId,
  { prepareChain = null, skipCommandWhenActive = false } = {},
) {
  const command = commandsById.get(commandId);
  if (!command || !editor || editor.isEditable === false) {
    return { active: false, disabled: true };
  }
  if (
    typeof command.available === "function" &&
    !command.available(editor)
  ) {
    return { active: false, disabled: true };
  }
  const active = commandIsActive(editor, command);
  if (command.action) {
    return {
      active,
      disabled: Boolean(
        command.actionRequiresSelection !== false &&
        editor.state?.selection?.empty &&
        !active,
      ),
    };
  }
  const chain = configuredChain(editor, command, {
    capability: true,
    prepareChain,
    skipCommand: skipCommandWhenActive && active,
  });
  return { active, disabled: !chain?.run?.() };
}

export function runEditorCommand(
  editor,
  commandId,
  {
    actions = {},
    trigger = null,
    prepareChain = null,
    skipCommandWhenActive = false,
  } = {},
) {
  const command = commandsById.get(commandId);
  if (!command || !editor || editor.isEditable === false) return false;
  if (
    typeof command.available === "function" &&
    !command.available(editor)
  ) {
    return false;
  }
  if (command.action) {
    const action = actions[command.action];
    return typeof action === "function" && Boolean(action({ command, editor, trigger }));
  }
  const chain = configuredChain(editor, command, {
    isolateHistory: command.history === "isolated",
    prepareChain,
    skipCommand: skipCommandWhenActive && commandIsActive(editor, command),
  });
  const ran = Boolean(chain?.run?.());
  if (ran && command.history === "isolated") closeEditorHistory(editor);
  return ran;
}
