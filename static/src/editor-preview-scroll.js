const MARKDOWN_FORMAT = "MARKDOWN";
const PREVIEW_LINES_ID = "editor-preview-block-lines";
const PREVIEW_CURSOR_RATIO = 2 / 3;
const PREVIEW_FOLLOW_STATES = new Set(["following", "paused"]);
const PREVIEW_SCROLL_KEYS = new Set([
  "ArrowDown",
  "ArrowUp",
  "End",
  "Home",
  "PageDown",
  "PageUp",
  " ",
]);

function clamp(value, minimum, maximum) {
  return Math.min(Math.max(value, minimum), maximum);
}

function scrollableHeight(viewportHeight, scrollHeight) {
  return Math.max(Number(scrollHeight) - Number(viewportHeight), 0);
}

export function previewScrollTop({ cursorTop, viewportHeight, scrollHeight }) {
  const viewport = Math.max(Number(viewportHeight) || 0, 0);
  const target = (Number(cursorTop) || 0) - viewport * PREVIEW_CURSOR_RATIO;
  return clamp(target, 0, scrollableHeight(viewport, scrollHeight));
}

export function previewScrollProgress({ scrollTop, viewportHeight, scrollHeight }) {
  const maximum = scrollableHeight(viewportHeight, scrollHeight);
  return maximum ? clamp((Number(scrollTop) || 0) / maximum, 0, 1) : 0;
}

export function scrollTopForPreviewProgress({ progress, viewportHeight, scrollHeight }) {
  return clamp(Number(progress) || 0, 0, 1) * scrollableHeight(viewportHeight, scrollHeight);
}

export function previewFollowTransition(current, event) {
  const state = PREVIEW_FOLLOW_STATES.has(current) ? current : "following";
  if (event === "manual") return "paused";
  if (event === "resume") return "following";
  return state;
}

export function blockIndexForLine(blockStartLines, line) {
  if (!blockStartLines.length) return 0;
  let low = 0;
  let high = blockStartLines.length - 1;
  while (low <= high) {
    const middle = Math.floor((low + high) / 2);
    if (blockStartLines[middle] <= line) low = middle + 1;
    else high = middle - 1;
  }
  return clamp(high, 0, blockStartLines.length - 1);
}

export function lineIndexForPosition(lineStarts, position) {
  if (!lineStarts.length) return 0;
  let low = 0;
  let high = lineStarts.length - 1;
  while (low <= high) {
    const middle = Math.floor((low + high) / 2);
    if (lineStarts[middle] <= position) low = middle + 1;
    else high = middle - 1;
  }
  return clamp(high, 0, lineStarts.length - 1);
}

function lineStartsFor(source) {
  const starts = [0];
  for (let index = 0; index < source.length; index += 1) {
    if (source.charCodeAt(index) === 10) starts.push(index + 1);
  }
  return starts;
}

function markdownLineFromViewport(source, lineStarts) {
  const scrollable = Math.max(source.scrollHeight - source.clientHeight, 0);
  if (!scrollable || lineStarts.length <= 1) return 0;
  const progress = clamp(source.scrollTop / scrollable, 0, 1);
  const lineHeight = Number.parseFloat(getComputedStyle(source).lineHeight) || 24;
  const visibleLines = Math.max(source.clientHeight / lineHeight, 1);
  const firstVisibleLine = progress * Math.max(lineStarts.length - visibleLines, 0);
  return Math.round(
    clamp(firstVisibleLine + visibleLines * PREVIEW_CURSOR_RATIO, 0, lineStarts.length - 1),
  );
}

function markdownBlockAnchor(blockStartLines, line, totalLines) {
  const index = blockIndexForLine(blockStartLines, line);
  const start = blockStartLines[index] || 0;
  const end =
    index + 1 < blockStartLines.length
      ? Math.max(blockStartLines[index + 1] - 1, start)
      : Math.max(totalLines - 1, start);
  return {
    index,
    blockRatio: clamp((line - start) / Math.max(end - start, 1), 0, 1),
  };
}

function previewBody(root) {
  const body = root.querySelector("[data-preview-body]");
  return body instanceof HTMLElement ? body : null;
}

function previewBlocks(body) {
  return Array.from(body.children).filter(
    (element) => !element.classList.contains("author-editor-preview__title"),
  );
}

function markdownBlockLines(root) {
  const script = root.querySelector(`#${PREVIEW_LINES_ID}`);
  if (!(script instanceof HTMLScriptElement)) return [];
  try {
    const values = JSON.parse(script.textContent || "[]");
    if (!Array.isArray(values)) return [];
    return values.filter(
      (value, index) =>
        Number.isInteger(value) && value >= 0 && (index === 0 || value > values[index - 1]),
    );
  } catch {
    return [];
  }
}

function tiptapSelectionAnchor(editor) {
  const position = editor?.state?.selection?.$from;
  const documentNode = editor?.state?.doc;
  if (!position || !documentNode?.childCount) return { index: 0, blockRatio: 0 };
  const index = clamp(position.index(0), 0, Math.max(documentNode.childCount - 1, 0));
  if (position.depth < 1) return { index, blockRatio: 0 };
  const block = documentNode.child(index);
  const blockStart = position.before(1) + 1;
  return {
    index,
    blockRatio: clamp(
      (position.pos - blockStart) / Math.max(block.content.size, 1),
      0,
      1,
    ),
  };
}

function visibleTiptapBlock(mount) {
  const content = mount.querySelector(".author-tiptap__content");
  if (!(content instanceof HTMLElement)) return { index: 0, blockRatio: 0 };
  const blocks = Array.from(content.children).filter(
    (element) => !element.hasAttribute("data-editor-block-controls"),
  );
  if (!blocks.length) return { index: 0, blockRatio: 0 };
  const mountRect = mount.getBoundingClientRect();
  const readingTop = mountRect.top + mount.clientHeight * PREVIEW_CURSOR_RATIO;
  let nearest = 0;
  let distance = Number.POSITIVE_INFINITY;
  let blockRatio = 0;
  blocks.forEach((block, index) => {
    const rect = block.getBoundingClientRect();
    const current =
      readingTop < rect.top
        ? rect.top - readingTop
        : readingTop > rect.bottom
          ? readingTop - rect.bottom
          : 0;
    if (current < distance) {
      nearest = index;
      distance = current;
      blockRatio = clamp((readingTop - rect.top) / Math.max(rect.height, 1), 0, 1);
    }
  });
  return { index: nearest, blockRatio };
}

function anchorIsDocumentStart(anchor) {
  return anchor.kind === "markdown" ? anchor.line === 0 : anchor.index === 0;
}

export function initializeEditorPreviewScroll({ root, source, format, tiptap }) {
  if (!(root instanceof HTMLFormElement) || !(source instanceof HTMLTextAreaElement)) {
    return null;
  }
  const tiptapMount = root.querySelector("[data-tiptap-editor]");
  let lineStarts = lineStartsFor(source.value);
  let frame = 0;
  let followState = "following";
  let manualProgress = 0;
  let boundBody = null;
  let boundResume = null;
  let anchor =
    format === MARKDOWN_FORMAT
      ? {
          kind: "markdown",
          line: lineIndexForPosition(lineStarts, source.selectionStart),
        }
      : {
          kind: "tiptap",
          ...tiptapSelectionAnchor(tiptap),
        };

  const updateFollowUi = () => {
    const preview = root.querySelector("[data-editor-preview]");
    if (preview instanceof HTMLElement) preview.dataset.previewFollow = followState;
    const resume = root.querySelector("[data-preview-follow-resume]");
    if (resume instanceof HTMLButtonElement) {
      resume.hidden = followState !== "paused";
      resume.setAttribute("aria-hidden", String(resume.hidden));
    }
  };

  const pauseFollow = () => {
    if (!(boundBody instanceof HTMLElement)) return;
    manualProgress = previewScrollProgress({
      scrollTop: boundBody.scrollTop,
      viewportHeight: boundBody.clientHeight,
      scrollHeight: boundBody.scrollHeight,
    });
    followState = previewFollowTransition(followState, "manual");
    updateFollowUi();
  };

  const trackManualScroll = () => {
    if (followState !== "paused" || !(boundBody instanceof HTMLElement)) return;
    manualProgress = previewScrollProgress({
      scrollTop: boundBody.scrollTop,
      viewportHeight: boundBody.clientHeight,
      scrollHeight: boundBody.scrollHeight,
    });
  };

  const pauseFromKeyboard = (event) => {
    if (PREVIEW_SCROLL_KEYS.has(event.key)) pauseFollow();
  };

  const resumeFollow = () => {
    followState = previewFollowTransition(followState, "resume");
    updateFollowUi();
    scheduleApply();
    requestAnimationFrame(() => boundBody?.focus({ preventScroll: true }));
  };

  const bindCurrentPreview = () => {
    const body = previewBody(root);
    if (body !== boundBody) {
      boundBody?.removeEventListener("wheel", pauseFollow);
      boundBody?.removeEventListener("touchstart", pauseFollow);
      boundBody?.removeEventListener("pointerdown", pauseFollow);
      boundBody?.removeEventListener("keydown", pauseFromKeyboard);
      boundBody?.removeEventListener("scroll", trackManualScroll);
      boundBody = body;
      boundBody?.addEventListener("wheel", pauseFollow, { passive: true });
      boundBody?.addEventListener("touchstart", pauseFollow, { passive: true });
      boundBody?.addEventListener("pointerdown", pauseFollow, { passive: true });
      boundBody?.addEventListener("keydown", pauseFromKeyboard);
      boundBody?.addEventListener("scroll", trackManualScroll, { passive: true });
    }
    const resume = root.querySelector("[data-preview-follow-resume]");
    if (resume !== boundResume) {
      boundResume?.removeEventListener("click", resumeFollow);
      boundResume = resume instanceof HTMLButtonElement ? resume : null;
      boundResume?.addEventListener("click", resumeFollow);
    }
    updateFollowUi();
    return body;
  };

  const apply = () => {
    frame = 0;
    const body = bindCurrentPreview();
    if (!body || body.clientHeight <= 0) return;
    const cursorOffset = body.clientHeight * PREVIEW_CURSOR_RATIO;
    const atDocumentStart = anchorIsDocumentStart(anchor);
    body.style.setProperty(
      "--editor-preview-tail-offset",
      `${body.clientHeight - cursorOffset}px`,
    );
    if (followState === "paused") {
      body.scrollTop = scrollTopForPreviewProgress({
        progress: manualProgress,
        viewportHeight: body.clientHeight,
        scrollHeight: body.scrollHeight,
      });
      return;
    }
    const blocks = previewBlocks(body);
    if (!blocks.length) return;
    let index;
    let blockRatio = anchor.blockRatio || 0;
    if (anchor.kind === "markdown") {
      const sourceLines = markdownBlockLines(root);
      if (sourceLines.length) {
        const sourceAnchor = markdownBlockAnchor(
          sourceLines,
          anchor.line,
          lineStarts.length,
        );
        if (sourceLines.length === blocks.length) {
          index = sourceAnchor.index;
          blockRatio = sourceAnchor.blockRatio;
        } else {
          const scaled =
            ((sourceAnchor.index + sourceAnchor.blockRatio) / sourceLines.length) *
            blocks.length;
          if (scaled >= blocks.length) {
            index = blocks.length - 1;
            blockRatio = 1;
          } else {
            index = Math.floor(scaled);
            blockRatio = scaled - index;
          }
        }
      } else {
        const scaled =
          (anchor.line / Math.max(lineStarts.length - 1, 1)) * blocks.length;
        if (scaled >= blocks.length) {
          index = blocks.length - 1;
          blockRatio = 1;
        } else {
          index = Math.floor(scaled);
          blockRatio = scaled - index;
        }
      }
    } else {
      index = anchor.index;
    }
    const block = blocks[clamp(index, 0, blocks.length - 1)];
    const bodyRect = body.getBoundingClientRect();
    const blockRect = block.getBoundingClientRect();
    const blockTop = body.scrollTop + blockRect.top - bodyRect.top;
    const cursorTop = blockTop + blockRect.height * clamp(blockRatio, 0, 1);
    body.scrollTop = atDocumentStart
      ? 0
      : previewScrollTop({
          cursorTop,
          viewportHeight: body.clientHeight,
          scrollHeight: body.scrollHeight,
        });
    body.querySelectorAll("img").forEach((image) => {
      if (image.complete || image.dataset.previewScrollBound === "true") return;
      image.dataset.previewScrollBound = "true";
      image.addEventListener("load", scheduleApply, { once: true });
      image.addEventListener("error", scheduleApply, { once: true });
    });
  };

  const scheduleApply = () => {
    if (frame) cancelAnimationFrame(frame);
    frame = requestAnimationFrame(apply);
  };

  const syncMarkdownSelection = () => {
    followState = previewFollowTransition(followState, "selection");
    anchor = {
      kind: "markdown",
      line: lineIndexForPosition(lineStarts, source.selectionStart),
    };
    scheduleApply();
  };

  const syncMarkdownInput = () => {
    followState = previewFollowTransition(followState, "content");
    lineStarts = lineStartsFor(source.value);
    syncMarkdownSelection();
  };

  const syncMarkdownViewport = () => {
    followState = previewFollowTransition(followState, "selection");
    anchor = {
      kind: "markdown",
      line: markdownLineFromViewport(source, lineStarts),
    };
    scheduleApply();
  };

  const syncTiptapSelection = () => {
    followState = previewFollowTransition(followState, "selection");
    anchor = {
      kind: "tiptap",
      ...tiptapSelectionAnchor(tiptap),
    };
    scheduleApply();
  };

  const syncTiptapViewport = () => {
    if (!(tiptapMount instanceof HTMLElement)) return;
    const visible = visibleTiptapBlock(tiptapMount);
    followState = previewFollowTransition(followState, "selection");
    anchor = { kind: "tiptap", ...visible };
    scheduleApply();
  };

  if (format === MARKDOWN_FORMAT) {
    source.addEventListener("input", syncMarkdownInput);
    source.addEventListener("click", syncMarkdownSelection);
    source.addEventListener("keyup", syncMarkdownSelection);
    source.addEventListener("select", syncMarkdownSelection);
    source.addEventListener("scroll", syncMarkdownViewport, { passive: true });
  } else if (tiptapMount instanceof HTMLElement) {
    tiptapMount.addEventListener("scroll", syncTiptapViewport, { passive: true });
  }
  scheduleApply();

  return {
    refresh: scheduleApply,
    syncSelection:
      format === MARKDOWN_FORMAT ? syncMarkdownSelection : syncTiptapSelection,
    dispose() {
      if (frame) cancelAnimationFrame(frame);
      if (format === MARKDOWN_FORMAT) {
        source.removeEventListener("input", syncMarkdownInput);
        source.removeEventListener("click", syncMarkdownSelection);
        source.removeEventListener("keyup", syncMarkdownSelection);
        source.removeEventListener("select", syncMarkdownSelection);
        source.removeEventListener("scroll", syncMarkdownViewport);
      } else if (tiptapMount instanceof HTMLElement) {
        tiptapMount.removeEventListener("scroll", syncTiptapViewport);
      }
      boundBody?.removeEventListener("wheel", pauseFollow);
      boundBody?.removeEventListener("touchstart", pauseFollow);
      boundBody?.removeEventListener("pointerdown", pauseFollow);
      boundBody?.removeEventListener("keydown", pauseFromKeyboard);
      boundBody?.removeEventListener("scroll", trackManualScroll);
      boundResume?.removeEventListener("click", resumeFollow);
    },
  };
}
