import { closeHistory } from "@tiptap/pm/history";

export function closeEditorHistory(editor) {
  const transaction = editor?.state?.tr;
  if (!transaction || typeof editor?.view?.dispatch !== "function") return false;
  closeHistory(transaction).setMeta("addToHistory", false);
  editor.view.dispatch(transaction);
  return true;
}

export function isolateEditorTransaction(transaction) {
  return closeHistory(transaction);
}

export function dispatchIsolatedEditorTransaction(
  editor,
  transaction,
  { focus = false } = {},
) {
  if (!transaction?.docChanged || typeof editor?.view?.dispatch !== "function") {
    return false;
  }
  editor.view.dispatch(isolateEditorTransaction(transaction));
  closeEditorHistory(editor);
  if (focus) editor.view.focus?.();
  return true;
}

export function isolateNextEditorInputHistory(editor) {
  const before = editor?.state?.doc;
  if (!before || !closeEditorHistory(editor)) return false;
  queueMicrotask(() => {
    if (editor.isDestroyed || editor.state?.doc === before) return;
    closeEditorHistory(editor);
  });
  return false;
}
