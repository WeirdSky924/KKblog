function normalizedText(value) {
  return value.normalize("NFKC").trim().toLocaleLowerCase("zh-CN");
}

function fuzzyMatch(value, query) {
  if (!query || value.includes(query)) return true;
  let queryIndex = 0;
  for (const character of value) {
    if (character === query[queryIndex]) queryIndex += 1;
    if (queryIndex === query.length) return true;
  }
  return false;
}

function pickerElements(root) {
  const elements = [];
  if (root instanceof HTMLElement && root.matches("[data-opportunity-filter-picker]")) {
    elements.push(root);
  }
  root.querySelectorAll?.("[data-opportunity-filter-picker]").forEach((picker) => {
    elements.push(picker);
  });
  return elements;
}

function initializePicker(picker) {
  if (!(picker instanceof HTMLElement) || picker.dataset.filterPickerBound === "true") {
    return;
  }
  const trigger = picker.querySelector("[data-opportunity-filter-trigger]");
  const dialog = picker.querySelector("[data-opportunity-filter-dialog]");
  const search = picker.querySelector("[data-opportunity-filter-search]");
  const summary = picker.querySelector("[data-opportunity-filter-summary]");
  const triggerCount = picker.querySelector("[data-opportunity-filter-trigger-count]");
  const footerCount = picker.querySelector("[data-opportunity-filter-count]");
  const clear = picker.querySelector("[data-opportunity-filter-clear]");
  const empty = picker.querySelector("[data-opportunity-filter-empty]");
  const options = Array.from(
    picker.querySelectorAll("[data-opportunity-filter-option]"),
  );
  const inputs = options
    .map((option) => option.querySelector("input[type='checkbox']"))
    .filter((input) => input instanceof HTMLInputElement);
  const displayMode = picker.dataset.opportunityFilterDisplay || "summary";
  const required = picker.dataset.opportunityFilterRequired === "true";
  if (
    !(trigger instanceof HTMLButtonElement) ||
    !(dialog instanceof HTMLDialogElement) ||
    !(search instanceof HTMLInputElement) ||
    !(clear instanceof HTMLButtonElement)
  ) {
    return;
  }
  picker.dataset.filterPickerBound = "true";

  const selectedOptions = () =>
    options.filter((option) => option.querySelector("input[type='checkbox']")?.checked);
  const signature = () => inputs.filter((input) => input.checked).map((input) => input.value).join("\u0000");
  let committedSelection = signature();

  const renderChipSummary = (names) => {
    if (!(summary instanceof HTMLElement)) return;
    summary.replaceChildren();
    if (!names.length) {
      const placeholder = document.createElement("span");
      placeholder.className = "opportunity-filter-picker__placeholder";
      placeholder.textContent = required ? "请选择" : "不限";
      summary.append(placeholder);
      return;
    }
    names.forEach((name) => {
      const chip = document.createElement("span");
      chip.className = "opportunity-filter-picker__chip";
      chip.textContent = name;
      summary.append(chip);
    });
  };

  const updateSelection = () => {
    const selected = selectedOptions();
    const names = selected.map((option) => option.dataset.opportunityFilterLabel || "");
    if (displayMode === "chips") {
      renderChipSummary(names);
    } else if (summary instanceof HTMLElement) {
      summary.textContent =
        names.length === 0
          ? required
            ? "请选择"
            : "不限"
          : names.length <= 2
            ? names.join("、")
            : `${names.slice(0, 2).join("、")} 等 ${names.length} 项`;
    }
    if (triggerCount instanceof HTMLElement) {
      triggerCount.textContent =
        displayMode === "chips"
          ? names.length
            ? "编辑"
            : "选择"
          : names.length
            ? `${names.length} 项`
            : "未选择";
    }
    if (footerCount instanceof HTMLElement) {
      footerCount.textContent = `已选择 ${names.length} 项`;
    }
    clear.disabled = names.length === 0;
    trigger.dataset.selected = String(names.length > 0);
  };

  const applySearch = () => {
    const query = normalizedText(search.value);
    let matches = 0;
    options.forEach((option) => {
      const label = normalizedText(option.dataset.opportunityFilterLabel || "");
      const matched = fuzzyMatch(label, query);
      option.hidden = !matched;
      if (matched) matches += 1;
    });
    if (empty instanceof HTMLElement) {
      empty.hidden = matches > 0 || !query;
    }
  };

  inputs.forEach((input) => input.addEventListener("change", updateSelection));
  search.addEventListener("input", applySearch);
  search.addEventListener("keydown", (event) => {
    if (event.key === "Enter") event.preventDefault();
  });
  trigger.addEventListener("click", () => {
    search.value = "";
    applySearch();
    dialog.showModal();
    requestAnimationFrame(() => search.focus());
  });
  clear.addEventListener("click", () => {
    inputs.forEach((input) => {
      input.checked = false;
    });
    updateSelection();
    search.focus();
  });
  dialog.querySelectorAll("[data-opportunity-filter-close], [data-opportunity-filter-done]").forEach((button) => {
    button.addEventListener("click", () => dialog.close());
  });
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
  dialog.addEventListener("close", () => {
    const currentSelection = signature();
    trigger.focus({ preventScroll: true });
    if (
      picker.dataset.opportunityFilterAutoSubmit === "true" &&
      currentSelection !== committedSelection
    ) {
      committedSelection = currentSelection;
      picker.closest("form")?.dispatchEvent(
        new CustomEvent("opportunity-filter-change", { bubbles: true }),
      );
    }
  });

  updateSelection();
  applySearch();
}

export function initializeOpportunityFilterPickers(root = document) {
  pickerElements(root).forEach(initializePicker);
}
