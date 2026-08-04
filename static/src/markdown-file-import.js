const UTF8_BOM_BYTES = 3;
const MARKDOWN_FILE_NAME = /\.md$/i;

export class MarkdownFileImportError extends Error {
  constructor(code) {
    super(code);
    this.name = "MarkdownFileImportError";
    this.code = code;
  }
}

function importError(code) {
  return new MarkdownFileImportError(code);
}

export async function readMarkdownFile(file, maximumBytes) {
  if (!(file instanceof File) || !MARKDOWN_FILE_NAME.test(file.name || "")) {
    throw importError("invalid_extension");
  }
  if (!Number.isSafeInteger(maximumBytes) || maximumBytes < 0) {
    throw importError("invalid_limit");
  }
  if (file.size > maximumBytes + UTF8_BOM_BYTES) {
    throw importError("too_large");
  }

  let source;
  try {
    const bytes = new Uint8Array(await file.arrayBuffer());
    source = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    throw importError("invalid_encoding");
  }
  if (source.startsWith("\uFEFF")) {
    source = source.slice(1);
  }
  if (source.includes("\u0000")) {
    throw importError("binary_content");
  }
  if (new TextEncoder().encode(source).byteLength > maximumBytes) {
    throw importError("too_large");
  }
  return source;
}
