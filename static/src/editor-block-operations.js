import { NodeSelection, Selection } from "@tiptap/pm/state";

import { dispatchIsolatedEditorTransaction } from "./editor-history.js";

function clampedPosition(doc, position) {
  const value = Number.isInteger(position) ? position : 0;
  return Math.min(Math.max(value, 0), doc.content.size);
}

export function topLevelBlockAtIndex(doc, index) {
  if (!doc || !Number.isInteger(index) || index < 0 || index >= doc.childCount) {
    return null;
  }
  let from = 0;
  for (let current = 0; current < index; current += 1) {
    from += doc.child(current).nodeSize;
  }
  const node = doc.child(index);
  return { index, from, to: from + node.nodeSize, node };
}

export function topLevelBlockAtPosition(doc, position) {
  if (!doc?.childCount) return null;
  const resolved = doc.resolve(clampedPosition(doc, position));
  const index = Math.min(resolved.index(0), doc.childCount - 1);
  return topLevelBlockAtIndex(doc, index);
}

function selectNear(transaction, position, bias = 1) {
  const safe = clampedPosition(transaction.doc, position);
  transaction.setSelection(Selection.near(transaction.doc.resolve(safe), bias));
  transaction.scrollIntoView();
  return transaction;
}

function selectTopLevel(transaction, position, bias = 1) {
  const safe = clampedPosition(transaction.doc, position);
  const node = transaction.doc.nodeAt(safe);
  if (node?.isAtom && NodeSelection.isSelectable(node)) {
    transaction.setSelection(NodeSelection.create(transaction.doc, safe));
    transaction.scrollIntoView();
    return transaction;
  }
  return selectNear(transaction, safe + 1, bias);
}

function dispatch(editor, transaction) {
  return dispatchIsolatedEditorTransaction(editor, transaction, { focus: true });
}

export function selectTopLevelBlock(editor, descriptor) {
  if (!editor || editor.isEditable === false || !descriptor) return false;
  const current = topLevelBlockAtIndex(editor.state.doc, descriptor.index);
  if (!current) return false;
  const transaction = selectTopLevel(editor.state.tr, current.from);
  transaction.setMeta("addToHistory", false);
  editor.view.dispatch(transaction);
  editor.view.focus();
  return true;
}

export function moveTopLevelBlock(editor, descriptor, targetIndex) {
  if (!editor || editor.isEditable === false || !descriptor) return false;
  const { doc } = editor.state;
  const current = topLevelBlockAtIndex(doc, descriptor.index);
  if (
    !current ||
    !Number.isInteger(targetIndex) ||
    targetIndex < 0 ||
    targetIndex >= doc.childCount ||
    targetIndex === current.index
  ) {
    return false;
  }

  let insertAt;
  if (targetIndex < current.index) {
    insertAt = topLevelBlockAtIndex(doc, targetIndex).from;
  } else {
    insertAt = current.from;
    for (let index = current.index + 1; index <= targetIndex; index += 1) {
      insertAt += doc.child(index).nodeSize;
    }
  }
  const transaction = editor.state.tr.delete(current.from, current.to);
  transaction.insert(insertAt, current.node);
  return dispatch(editor, selectTopLevel(transaction, insertAt));
}

export function runTopLevelBlockOperation(editor, descriptor, operation) {
  if (!editor || editor.isEditable === false || !descriptor) return false;
  const current = topLevelBlockAtIndex(editor.state.doc, descriptor.index);
  if (!current) return false;

  if (operation === "up" || operation === "down") {
    const offset = operation === "up" ? -1 : 1;
    return moveTopLevelBlock(editor, current, current.index + offset);
  }
  if (operation === "copy") {
    const transaction = editor.state.tr.insert(current.to, current.node);
    return dispatch(editor, selectTopLevel(transaction, current.to));
  }
  if (operation !== "delete") return false;

  if (editor.state.doc.childCount === 1) {
    const paragraph = editor.state.schema.nodes.paragraph;
    if (!paragraph) return false;
    const transaction = editor.state.tr.replaceWith(
      0,
      editor.state.doc.content.size,
      paragraph.create(),
    );
    return dispatch(editor, selectTopLevel(transaction, 0));
  }

  const transaction = editor.state.tr.delete(current.from, current.to);
  const bias = current.from >= transaction.doc.content.size ? -1 : 1;
  return dispatch(editor, selectNear(transaction, current.from, bias));
}
