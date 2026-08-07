import assert from "node:assert/strict";
import test from "node:test";

import {
  MarkdownFileImportError,
  readMarkdownFile,
} from "../../static/src/markdown-file-import.js";

test("reads UTF-8 Markdown and removes one leading BOM", async () => {
  const file = new File(["\uFEFF# 标题\n\n正文"], "article.MD", {
    type: "application/octet-stream",
  });

  assert.equal(await readMarkdownFile(file, 1024), "# 标题\n\n正文");
});

test("rejects a file whose name does not end in .md", async () => {
  const file = new File(["正文"], "article.txt", { type: "text/markdown" });

  await assert.rejects(
    readMarkdownFile(file, 1024),
    (error) =>
      error instanceof MarkdownFileImportError && error.code === "invalid_extension",
  );
});

test("rejects Markdown above the configured body byte limit", async () => {
  const file = new File(["12345"], "article.md", { type: "text/markdown" });

  await assert.rejects(
    readMarkdownFile(file, 4),
    (error) =>
      error instanceof MarkdownFileImportError && error.code === "too_large",
  );
});

test("accepts a UTF-8 BOM outside the body byte limit", async () => {
  const file = new File([new Uint8Array([0xef, 0xbb, 0xbf]), "1234"], "article.md");

  assert.equal(await readMarkdownFile(file, 4), "1234");
});

test("rejects malformed UTF-8 and NUL bytes", async () => {
  const malformed = new File([new Uint8Array([0xc3, 0x28])], "broken.md");
  const binary = new File(["safe\u0000unsafe"], "binary.md");

  await assert.rejects(
    readMarkdownFile(malformed, 1024),
    (error) =>
      error instanceof MarkdownFileImportError && error.code === "invalid_encoding",
  );
  await assert.rejects(
    readMarkdownFile(binary, 1024),
    (error) =>
      error instanceof MarkdownFileImportError && error.code === "binary_content",
  );
});
