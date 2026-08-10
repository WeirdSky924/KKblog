const ULID = /^[0-9A-HJKMNP-TV-Z]{26}$/;
const MEDIA_SOURCE = /^media:([0-9A-HJKMNP-TV-Z]{26})$/;
const MAX_NODES = 10_000;

function tiptapAttachmentIds(body) {
  let document;
  try {
    document = JSON.parse(body);
  } catch {
    return null;
  }
  if (!document || typeof document !== "object" || Array.isArray(document)) {
    return null;
  }
  const stack = [document];
  const attachmentIds = [];
  let visited = 0;
  while (stack.length) {
    const node = stack.pop();
    visited += 1;
    if (visited > MAX_NODES || !node || typeof node !== "object") return null;
    if (node.type === "attachment") {
      const match = String(node.attrs?.src || "").match(MEDIA_SOURCE);
      if (!match) return null;
      attachmentIds.push(match[1]);
      if (attachmentIds.length > 1) return null;
    }
    if (node.content !== undefined && !Array.isArray(node.content)) return null;
    for (const child of node.content || []) stack.push(child);
  }
  return attachmentIds;
}

export function draftAttachmentAssetId(format, values) {
  if (!values || typeof values !== "object" || typeof values.body !== "string") {
    return null;
  }
  const hasExplicit = Object.hasOwn(values, "attachmentAssetId");
  const explicit = hasExplicit ? values.attachmentAssetId : undefined;
  if (
    hasExplicit &&
    (typeof explicit !== "string" || (explicit !== "" && !ULID.test(explicit)))
  ) {
    return null;
  }
  if (format === "MARKDOWN") return hasExplicit ? explicit : "";
  if (format !== "TIPTAP_JSON") return null;
  const attachmentIds = tiptapAttachmentIds(values.body);
  if (attachmentIds === null) return null;
  const fromBody = attachmentIds[0] || "";
  if (hasExplicit && fromBody && explicit !== fromBody) return null;
  return hasExplicit ? explicit : fromBody;
}
