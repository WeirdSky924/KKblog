const DRAFT_SCHEMA = "kaj.authoring.draft.v1";
const DRAFT_PREFIX = `${DRAFT_SCHEMA}:`;
const PENDING_SAVE_KEY = "kaj.authoring.pending-cloud-save.v1";
const SAVE_DELAY_MS = 500;
const ULID = /^[0-9A-HJKMNP-TV-Z]{26}$/;
const USER_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const FORMATS = new Set(["MARKDOWN", "TIPTAP_JSON"]);
function identityFor(form) {
  const identity = {
    userId: form.dataset.editorUserId || "",
    articleKey: form.dataset.editorArticleKey || "",
    baselineRevisionId: form.dataset.editorBaseline || "",
    format: form.dataset.authorEditor || "",
    mode: form.dataset.editorMode || "",
  };
  if (
    !USER_ID.test(identity.userId) ||
    !ULID.test(identity.articleKey) ||
    !(identity.baselineRevisionId === "NEW" || ULID.test(identity.baselineRevisionId)) ||
    !FORMATS.has(identity.format) ||
    !["create", "edit"].includes(identity.mode)
  ) {
    return null;
  }
  return identity;
}
function keyFor(identity) {
  return [
    DRAFT_SCHEMA,
    identity.userId,
    identity.articleKey,
    identity.baselineRevisionId,
    identity.format,
  ].join(":");
}
function localLabel(form) {
  return form.querySelector("[data-editor-local-state]");
}
function setLocalState(form, state, text) {
  const label = localLabel(form);
  if (!(label instanceof HTMLElement)) return;
  label.dataset.localState = state;
  label.textContent = text;
}
function field(form, name) {
  const value = form.elements.namedItem(name);
  return value instanceof HTMLInputElement ||
    value instanceof HTMLTextAreaElement ||
    value instanceof HTMLSelectElement
    ? value
    : null;
}
function checked(form, name) {
  const input = field(form, name);
  return input instanceof HTMLInputElement && input.checked;
}
function valuesFrom(form) {
  return {
    title: field(form, "title")?.value || "",
    body: field(form, "body")?.value || "",
    summaryMode: field(form, "summary_mode")?.value || "",
    customSummary: field(form, "custom_summary")?.value || "",
    visibility: field(form, "visibility")?.value || "",
    sectionId: field(form, "section_id")?.value || "",
    tagIds: Array.from(form.querySelectorAll("input[name='tag_ids']:checked"), (item) => item.value),
    coverAssetId: field(form, "cover_asset_id")?.value || "",
    commentsEnabled: checked(form, "comments_enabled"),
    commentsViewLogin: checked(form, "comments_view_login"),
    commentsPostLogin: checked(form, "comments_post_login"),
  };
}
function validValues(values) {
  const strings = [
    "title",
    "body",
    "summaryMode",
    "customSummary",
    "visibility",
    "sectionId",
    "coverAssetId",
  ];
  return (
    values &&
    typeof values === "object" &&
    strings.every((name) => typeof values[name] === "string") &&
    Array.isArray(values.tagIds) &&
    values.tagIds.length <= 10 &&
    values.tagIds.every((value) => typeof value === "string") &&
    ["commentsEnabled", "commentsViewLogin", "commentsPostLogin"].every(
      (name) => typeof values[name] === "boolean",
    )
  );
}
function validDraft(draft, identity) {
  return (
    draft?.schema === DRAFT_SCHEMA &&
    draft.userId === identity.userId &&
    draft.articleKey === identity.articleKey &&
    draft.baselineRevisionId === identity.baselineRevisionId &&
    draft.format === identity.format &&
    Number.isSafeInteger(draft.savedAt) &&
    validValues(draft.values)
  );
}
function setChoice(form, name, value) {
  const control = field(form, name);
  if (control instanceof HTMLSelectElement) {
    if (Array.from(control.options).some((option) => option.value === value)) {
      control.value = value;
    }
    return;
  }
  if (control) control.value = value;
}
function syncCoverPreview(form, assetId) {
  const picker = form.querySelector("[data-media-picker='article-cover']");
  const preview = picker?.querySelector("[data-media-preview]");
  const empty = picker?.querySelector("[data-media-empty]");
  if (!(preview instanceof HTMLImageElement)) return;
  if (ULID.test(assetId)) {
    preview.src = `/_kaj/media/${assetId}`;
    preview.alt = "文章封面预览";
    preview.hidden = false;
    if (empty instanceof HTMLElement) empty.hidden = true;
  } else {
    preview.removeAttribute("src");
    preview.alt = "";
    preview.hidden = true;
    if (empty instanceof HTMLElement) empty.hidden = false;
  }
}

function applyDraft(form, values) {
  setChoice(form, "title", values.title);
  setChoice(form, "body", values.body);
  setChoice(form, "summary_mode", values.summaryMode);
  setChoice(form, "custom_summary", values.customSummary);
  setChoice(form, "visibility", values.visibility);
  setChoice(form, "section_id", values.sectionId);
  setChoice(form, "cover_asset_id", values.coverAssetId);
  const selectedTags = new Set(values.tagIds);
  form.querySelectorAll("input[name='tag_ids']").forEach((input) => {
    input.checked = selectedTags.has(input.value);
  });
  [
    ["comments_enabled", values.commentsEnabled],
    ["comments_view_login", values.commentsViewLogin],
    ["comments_post_login", values.commentsPostLogin],
  ].forEach(([name, value]) => {
    const input = field(form, name);
    if (input instanceof HTMLInputElement) input.checked = value;
  });
  syncCoverPreview(form, values.coverAssetId);
}

function parseStored(storage, key) {
  const serialized = storage.getItem(key);
  return serialized === null ? null : JSON.parse(serialized);
}

function acknowledgeSuccessfulPending(form, identity) {
  if (form.dataset.cloudSaved !== "true") return true;
  try {
    const pending = parseStored(window.sessionStorage, PENDING_SAVE_KEY);
    if (
      pending?.schema === DRAFT_SCHEMA &&
      pending.userId === identity.userId &&
      pending.format === identity.format &&
      (pending.articleKey === identity.articleKey || pending.mode === "create") &&
      typeof pending.key === "string" &&
      pending.key.startsWith(DRAFT_PREFIX)
    ) {
      window.sessionStorage.removeItem(PENDING_SAVE_KEY);
    }
    return true;
  } catch {
    return false;
  }
}

function preserveCreateScope(identity) {
  if (identity.mode !== "create") return;
  const url = new URL(window.location.href);
  if (url.searchParams.get("scope") === identity.articleKey) return;
  url.searchParams.set("scope", identity.articleKey);
  window.history.replaceState(window.history.state, "", url);
}

export function initializeLocalDraft(form) {
  const identity = identityFor(form);
  if (!identity) {
    setLocalState(form, "error", "本地保存不可用");
    return null;
  }
  const key = keyFor(identity);
  let timer = null;
  let dirty = false;
  let restored = false;

  preserveCreateScope(identity);
  const cloudSaveAcknowledged = acknowledgeSuccessfulPending(form, identity);
  const skipLocalRestore = form.dataset.editorSkipLocalRestore === "true";
  const conflictBaseline = form.dataset.editorConflictLocalBaseline || "";
  try {
    if (conflictBaseline && !ULID.test(conflictBaseline)) {
      throw new Error("invalid conflict baseline");
    }
    const recoveryIdentity = conflictBaseline
      ? { ...identity, baselineRevisionId: conflictBaseline }
      : skipLocalRestore
        ? null
        : identity;
    const draft = recoveryIdentity
      ? parseStored(window.localStorage, keyFor(recoveryIdentity))
      : null;
    if (draft !== null && recoveryIdentity !== null) {
      if (!validDraft(draft, recoveryIdentity)) throw new Error("invalid local draft");
      applyDraft(form, draft.values);
      restored = true;
      setLocalState(
        form,
        "restored",
        conflictBaseline ? "已保留冲突前本地稿" : "已恢复本地稿",
      );
    } else if (conflictBaseline) {
      setLocalState(form, "error", "冲突前本地稿不可用，已加载所选云端版本");
    } else if (!cloudSaveAcknowledged) {
      setLocalState(form, "error", "云端保存状态无法确认，本地稿仍保留");
    }
  } catch {
    setLocalState(form, "error", "本地稿无法读取");
  }

  const write = () => {
    window.clearTimeout(timer);
    timer = null;
    try {
      window.localStorage.setItem(
        key,
        JSON.stringify({
          schema: DRAFT_SCHEMA,
          userId: identity.userId,
          articleKey: identity.articleKey,
          baselineRevisionId: identity.baselineRevisionId,
          format: identity.format,
          savedAt: Date.now(),
          values: valuesFrom(form),
        }),
      );
      dirty = false;
      setLocalState(form, "saved", "已保存到本地");
      return true;
    } catch {
      setLocalState(form, "error", "本地保存失败");
      return false;
    }
  };

  const schedule = () => {
    dirty = true;
    setLocalState(form, "pending", "等待本地保存");
    window.clearTimeout(timer);
    timer = window.setTimeout(write, SAVE_DELAY_MS);
  };

  const flushForCloudSave = () => {
    write();
    try {
      window.sessionStorage.setItem(
        PENDING_SAVE_KEY,
        JSON.stringify({ schema: DRAFT_SCHEMA, key, ...identity }),
      );
    } catch {
      // The local draft remains intact even when per-tab storage is unavailable.
    }
  };

  const pagehide = () => {
    if (dirty) write();
  };
  window.addEventListener("pagehide", pagehide);

  return {
    restored,
    schedule,
    flushForCloudSave,
    dispose() {
      window.clearTimeout(timer);
      window.removeEventListener("pagehide", pagehide);
    },
  };
}

export function clearArticleLocalDrafts({ userId, articleKey }) {
  if (!USER_ID.test(userId) || !ULID.test(articleKey)) {
    return { ok: false, cleared: 0, pendingCleared: false };
  }
  const prefix = `${DRAFT_SCHEMA}:${userId}:${articleKey}:`;
  let cleared = 0;
  let pendingCleared = false;
  try {
    const keys = Array.from({ length: window.localStorage.length }, (_, index) =>
      window.localStorage.key(index),
    ).filter((key) => key?.startsWith(prefix));
    keys.forEach((key) => {
      window.localStorage.removeItem(key);
      cleared += 1;
    });
    const pending = parseStored(window.sessionStorage, PENDING_SAVE_KEY);
    if (
      pending?.schema === DRAFT_SCHEMA &&
      pending.userId === userId &&
      pending.articleKey === articleKey
    ) {
      window.sessionStorage.removeItem(PENDING_SAVE_KEY);
      pendingCleared = true;
    }
    return { ok: true, cleared, pendingCleared };
  } catch {
    return { ok: false, cleared, pendingCleared };
  }
}

document.addEventListener("kaj:author-draft-clear", (event) => {
  if (event.detail?.userId && event.detail?.articleKey) {
    const result = clearArticleLocalDrafts(event.detail);
    const status = document.querySelector("[data-author-draft-clear-result]");
    if (status instanceof HTMLElement) {
      status.textContent = result.ok
        ? "这个浏览器中的对应本地稿已清理。"
        : "云端草稿已删除，但本地稿未能清理，请清除浏览器站点数据。";
      status.dataset.localState = result.ok ? "cleared" : "error";
    }
  }
});

export function initializeArticleDraftClears(root = document) {
  const markers = [];
  if (root instanceof HTMLElement && root.matches("[data-author-draft-clear-request]")) {
    markers.push(root);
  }
  root.querySelectorAll?.("[data-author-draft-clear-request]").forEach((item) =>
    markers.push(item),
  );
  markers.forEach((marker) => {
    if (!(marker instanceof HTMLElement) || marker.dataset.clearDispatched === "true") {
      return;
    }
    marker.dataset.clearDispatched = "true";
    document.dispatchEvent(
      new CustomEvent("kaj:author-draft-clear", {
        detail: {
          userId: marker.dataset.userId,
          articleKey: marker.dataset.articleKey,
        },
      }),
    );
  });
}
