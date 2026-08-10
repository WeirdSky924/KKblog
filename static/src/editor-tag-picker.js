const MAX_TAGS = 10;

function normalizedName(value) {
  return value.normalize("NFKC").trim().toLocaleLowerCase("zh-CN");
}

function fuzzyMatch(name, query) {
  if (!query || name.includes(query)) return true;
  let queryIndex = 0;
  for (const character of name) {
    if (character === query[queryIndex]) queryIndex += 1;
    if (queryIndex === query.length) return true;
  }
  return false;
}

function parsedProposals(input) {
  try {
    const values = JSON.parse(input.value || "[]");
    if (!Array.isArray(values)) return [];
    const seen = new Set();
    return values.filter((value) => {
      if (typeof value !== "string") return false;
      const normalized = normalizedName(value);
      if (!normalized || value.normalize("NFKC").trim().length > 50 || seen.has(normalized)) {
        return false;
      }
      seen.add(normalized);
      return true;
    });
  } catch {
    return [];
  }
}

function labelText(input) {
  const label = input.closest("label");
  return label?.textContent?.trim().replace(/（待审核）$/, "") || "";
}

function initializeTagPicker(form) {
  const dialog = form.querySelector("[data-tag-picker-dialog]");
  const trigger = form.querySelector("[data-tag-picker-trigger]");
  const search = form.querySelector("[data-tag-picker-search]");
  const proposal = form.querySelector("[data-tag-picker-proposal]");
  const proposalLabel = form.querySelector("[data-tag-picker-proposal-label]");
  const proposedContainer = form.querySelector("[data-tag-picker-proposed]");
  const proposedInput = form.querySelector("[data-proposed-tag-names]");
  const status = form.querySelector("[data-tag-picker-status]");
  const empty = form.querySelector("[data-tag-picker-empty]");
  const summary = form.querySelector("[data-tag-picker-summary]");
  const countLabels = form.querySelectorAll(
    "[data-editor-tag-count], [data-tag-picker-footer-count]",
  );
  const existingInputs = Array.from(form.querySelectorAll("input[name='tag_ids']"));
  if (
    !(dialog instanceof HTMLDialogElement) ||
    !(trigger instanceof HTMLButtonElement) ||
    !(search instanceof HTMLInputElement) ||
    !(proposal instanceof HTMLButtonElement) ||
    !(proposalLabel instanceof HTMLElement) ||
    !(proposedContainer instanceof HTMLElement) ||
    !(proposedInput instanceof HTMLInputElement) ||
    form.dataset.tagPickerBound === "true"
  ) {
    return;
  }
  form.dataset.tagPickerBound = "true";

  const existingNames = new Map(
    existingInputs.map((input) => [normalizedName(labelText(input)), input]),
  );
  const proposals = new Map(
    parsedProposals(proposedInput)
      .map((name) => [normalizedName(name), name.normalize("NFKC").trim()])
      .filter(([normalized]) => !existingNames.has(normalized)),
  );
  proposedInput.value = JSON.stringify(Array.from(proposals.values()));

  const selectedCount = () =>
    existingInputs.filter((input) => input.checked).length + proposals.size;

  const setStatus = (message = "", state = "") => {
    if (!(status instanceof HTMLElement)) return;
    status.textContent = message;
    status.dataset.state = state;
  };

  const syncInput = () => {
    proposedInput.value = JSON.stringify(Array.from(proposals.values()));
    proposedInput.dispatchEvent(new Event("input", { bubbles: true }));
  };

  const selectedNames = () => [
    ...existingInputs.filter((input) => input.checked).map(labelText),
    ...proposals.values(),
  ];

  const updateSummary = () => {
    const count = selectedCount();
    countLabels.forEach((item) => {
      item.textContent = `已选择 ${count} / ${MAX_TAGS}`;
    });
    if (summary instanceof HTMLElement) {
      const names = selectedNames();
      summary.textContent =
        names.length === 0
          ? "选择文章标签"
          : names.length <= 2
            ? names.join("、")
            : `${names.slice(0, 2).join("、")} 等 ${names.length} 个`;
    }
    const atLimit = count >= MAX_TAGS;
    existingInputs.forEach((input) => {
      input.disabled = atLimit && !input.checked;
    });
  };

  const proposedRow = (name) => {
    const row = document.createElement("label");
    row.className = "author-tag-picker__option author-tag-picker__option--proposed";
    row.dataset.tagPickerOption = normalizedName(name);
    const input = document.createElement("input");
    input.type = "checkbox";
    input.checked = true;
    input.dataset.proposedTagCheckbox = normalizedName(name);
    const text = document.createElement("span");
    text.textContent = name;
    const badge = document.createElement("small");
    badge.textContent = "待申请";
    row.append(input, text, badge);
    input.addEventListener("change", () => {
      proposals.delete(input.dataset.proposedTagCheckbox || "");
      row.remove();
      syncInput();
      updateSummary();
      applyFilter();
      setStatus(`已取消申请「${name}」`);
    });
    return row;
  };

  const renderProposals = () => {
    proposedContainer.replaceChildren(...Array.from(proposals.values(), proposedRow));
  };

  const applyFilter = () => {
    const query = normalizedName(search.value);
    let matches = 0;
    existingInputs.forEach((input) => {
      const wrapper = input.closest("div");
      const matched = fuzzyMatch(normalizedName(labelText(input)), query);
      if (wrapper instanceof HTMLElement) wrapper.hidden = !matched;
      if (matched) matches += 1;
    });
    proposedContainer.querySelectorAll("[data-tag-picker-option]").forEach((row) => {
      const matched = fuzzyMatch(row.dataset.tagPickerOption || "", query);
      row.hidden = !matched;
      if (matched) matches += 1;
    });

    const display = search.value.normalize("NFKC").trim();
    const valid = display.length > 0 && display.length <= 50 && !/[\u0000-\u001f]/.test(display);
    const exact = existingNames.has(query) || proposals.has(query);
    const canPropose = valid && !exact;
    proposal.hidden = !canPropose;
    proposal.disabled = selectedCount() >= MAX_TAGS;
    proposalLabel.textContent = canPropose
      ? selectedCount() >= MAX_TAGS
        ? "已达到 10 个标签上限"
        : `申请并选择「${display}」`
      : "";
    proposal.dataset.proposalName = canPropose ? display : "";
    if (empty instanceof HTMLElement) empty.hidden = matches > 0 || canPropose || !query;
  };

  existingInputs.forEach((input) => {
    input.addEventListener("change", () => {
      if (input.checked && selectedCount() > MAX_TAGS) {
        input.checked = false;
        setStatus("每篇文章最多选择 10 个标签。", "error");
      } else {
        setStatus(input.checked ? `已选择「${labelText(input)}」` : `已取消「${labelText(input)}」`);
      }
      updateSummary();
      applyFilter();
    });
  });

  proposal.addEventListener("click", () => {
    const name = proposal.dataset.proposalName || "";
    const normalized = normalizedName(name);
    if (!name || proposals.has(normalized) || existingNames.has(normalized)) return;
    if (selectedCount() >= MAX_TAGS) {
      setStatus("每篇文章最多选择 10 个标签。", "error");
      return;
    }
    proposals.set(normalized, name);
    renderProposals();
    syncInput();
    search.value = "";
    updateSummary();
    applyFilter();
    setStatus(`已申请并选择「${name}」`);
    search.focus();
  });

  search.addEventListener("input", () => {
    setStatus();
    applyFilter();
  });
  trigger.addEventListener("click", () => {
    dialog.showModal();
    requestAnimationFrame(() => {
      search.focus();
      search.select();
    });
  });
  dialog.querySelectorAll("[data-tag-picker-close], [data-tag-picker-done]").forEach((button) => {
    button.addEventListener("click", () => dialog.close());
  });
  dialog.addEventListener("close", () => trigger.focus({ preventScroll: true }));
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });

  renderProposals();
  updateSummary();
  applyFilter();
}

export function initializeEditorTagPickers(scope = document) {
  if (scope instanceof HTMLFormElement && scope.matches("form[data-author-editor]")) {
    initializeTagPicker(scope);
  }
  scope.querySelectorAll?.("form[data-author-editor]").forEach(initializeTagPicker);
}
