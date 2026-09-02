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
  if (!(input instanceof HTMLInputElement)) return [];
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
  const filterPicker = form.matches("[data-tag-filter-picker]");
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
    "[data-editor-tag-count], [data-tag-picker-footer-count], [data-tag-picker-filter-count]",
  );
  const existingInputs = Array.from(
    form.querySelectorAll("input[name='tag_ids'], input[name='tags']"),
  );
  const maxTags = Number.parseInt(form.dataset.tagPickerLimit || "", 10) || MAX_TAGS;
  if (
    !(dialog instanceof HTMLDialogElement) ||
    !(trigger instanceof HTMLButtonElement) ||
    !(search instanceof HTMLInputElement) ||
    (!filterPicker && !(proposal instanceof HTMLButtonElement)) ||
    (!filterPicker && !(proposalLabel instanceof HTMLElement)) ||
    (!filterPicker && !(proposedContainer instanceof HTMLElement)) ||
    (!filterPicker && !(proposedInput instanceof HTMLInputElement)) ||
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
  if (proposedInput instanceof HTMLInputElement) {
    proposedInput.value = JSON.stringify(Array.from(proposals.values()));
  }

  const signature = () =>
    existingInputs
      .filter((input) => input.checked)
      .map((input) => input.value)
      .join("\u0000");
  let committedSelection = signature();

  const selectedCount = () =>
    existingInputs.filter((input) => input.checked).length + proposals.size;

  const setStatus = (message = "", state = "") => {
    if (!(status instanceof HTMLElement)) return;
    status.textContent = message;
    status.dataset.state = state;
  };

  const syncInput = () => {
    if (!(proposedInput instanceof HTMLInputElement)) return;
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
      item.textContent = `已选择 ${count} / ${maxTags}`;
    });
    if (summary instanceof HTMLElement) {
      const names = selectedNames();
      summary.textContent =
        names.length === 0
          ? filterPicker
            ? "选择标签"
            : "选择文章标签"
          : names.length <= 2
            ? names.join("、")
            : `${names.slice(0, 2).join("、")} 等 ${names.length} 个`;
    }
    const atLimit = count >= maxTags;
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
    if (proposedContainer instanceof HTMLElement) {
      proposedContainer.querySelectorAll("[data-tag-picker-option]").forEach((row) => {
        const matched = fuzzyMatch(row.dataset.tagPickerOption || "", query);
        row.hidden = !matched;
        if (matched) matches += 1;
      });
    }

    const display = search.value.normalize("NFKC").trim();
    const valid = display.length > 0 && display.length <= 50 && !/[\u0000-\u001f]/.test(display);
    const exact = existingNames.has(query) || proposals.has(query);
    const canPropose = valid && !exact;
    if (proposal instanceof HTMLButtonElement && proposalLabel instanceof HTMLElement) {
      proposal.hidden = !canPropose;
      proposal.disabled = selectedCount() >= maxTags;
      proposalLabel.textContent = canPropose
        ? selectedCount() >= maxTags
          ? `已达到 ${maxTags} 个标签上限`
          : `申请并选择「${display}」`
        : "";
      proposal.dataset.proposalName = canPropose ? display : "";
    }
    if (empty instanceof HTMLElement) {
      empty.hidden = matches > 0 || (!filterPicker && canPropose) || !query;
    }
  };

  existingInputs.forEach((input) => {
    input.addEventListener("change", (event) => {
      if (filterPicker) event.stopPropagation();
      if (input.checked && selectedCount() > maxTags) {
        input.checked = false;
        setStatus(`最多选择 ${maxTags} 个标签。`, "error");
      } else {
        setStatus(input.checked ? `已选择「${labelText(input)}」` : `已取消「${labelText(input)}」`);
      }
      updateSummary();
      applyFilter();
    });
  });

  if (proposal instanceof HTMLButtonElement) {
    proposal.addEventListener("click", () => {
      const name = proposal.dataset.proposalName || "";
      const normalized = normalizedName(name);
      if (!name || proposals.has(normalized) || existingNames.has(normalized)) return;
      if (selectedCount() >= maxTags) {
        setStatus(`每篇文章最多选择 ${maxTags} 个标签。`, "error");
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
  }

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
  dialog.addEventListener("close", () => {
    trigger.focus({ preventScroll: true });
    if (!filterPicker) return;
    const currentSelection = signature();
    if (currentSelection === committedSelection) return;
    committedSelection = currentSelection;
    form.closest("form")?.dispatchEvent(
      new CustomEvent("tag-filter-change", { bubbles: true }),
    );
  });
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });

  if (proposedInput instanceof HTMLInputElement) renderProposals();
  updateSummary();
  applyFilter();
}

export function initializeEditorTagPickers(scope = document) {
  if (
    scope instanceof HTMLElement &&
    (scope.matches("form[data-author-editor]") || scope.matches("[data-tag-filter-picker]"))
  ) {
    initializeTagPicker(scope);
  }
  scope
    .querySelectorAll?.("form[data-author-editor], [data-tag-filter-picker]")
    .forEach(initializeTagPicker);
}
