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

function submitOpportunityFilter(form) {
  if (!(form instanceof HTMLFormElement)) return;
  if (typeof form.requestSubmit === "function") {
    form.requestSubmit();
    return;
  }
  form.dispatchEvent(
    new CustomEvent("opportunity-filter-change", { bubbles: true }),
  );
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
  const more = picker.querySelector("[data-opportunity-filter-more]");
  const optionsContainer = picker.querySelector("[data-opportunity-filter-options]");
  const empty = picker.querySelector("[data-opportunity-filter-empty]");
  let options = Array.from(picker.querySelectorAll("[data-opportunity-filter-option]"));
  const lazy = picker.dataset.opportunityFilterLazy === "true";
  const optionName = picker.dataset.opportunityFilterName || "";
  let lazyPage = 0;
  let lazyQuery = "";
  let lazyHasMore = false;
  let lazyLoading = false;
  let lazyReloadPending = false;
  let lazyTimer = 0;
  let lazyRequest = 0;
  const selectedLabels = new Map();
  const displayMode = picker.dataset.opportunityFilterDisplay || "summary";
  const required = picker.dataset.opportunityFilterRequired === "true";
  if (
    !(trigger instanceof HTMLButtonElement) ||
    !(dialog instanceof HTMLDialogElement) ||
    !(search instanceof HTMLInputElement) ||
    !(clear instanceof HTMLButtonElement) ||
    !(optionsContainer instanceof HTMLElement)
  ) {
    return;
  }
  picker.dataset.filterPickerBound = "true";

  const inputs = () =>
    options
      .map((option) => option.querySelector("input[type='checkbox']"))
      .filter((input) => input instanceof HTMLInputElement);
  const selectedOptions = () =>
    options.filter((option) => option.querySelector("input[type='checkbox']")?.checked);
  const signature = () =>
    inputs()
      .filter((input) => input.checked)
      .map((input) => input.value)
      .join("\u0000");
  let committedSelection = signature();

  options.forEach((option) => {
    const input = option.querySelector("input[type='checkbox']");
    const label = option.dataset.opportunityFilterLabel || "";
    if (input instanceof HTMLInputElement && input.checked) {
      selectedLabels.set(input.value, label);
    }
  });

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

  const renderLazyOptions = (items, { append = false } = {}) => {
    const records = new Map();
    if (append) {
      options.forEach((option) => {
        const input = option.querySelector("input[type='checkbox']");
        if (input instanceof HTMLInputElement) {
          records.set(input.value, option.dataset.opportunityFilterLabel || "");
        }
      });
    }
    items.forEach((item) => {
      if (item && typeof item.value === "string" && typeof item.label === "string") {
        records.set(item.value, item.label);
      }
    });
    selectedLabels.forEach((label, value) => {
      if (!records.has(value)) records.set(value, label);
    });
    optionsContainer.replaceChildren();
    records.forEach((label, value) => {
      const option = document.createElement("label");
      option.dataset.opportunityFilterOption = "";
      option.dataset.opportunityFilterLabel = label;
      const input = document.createElement("input");
      input.type = "checkbox";
      input.name = optionName;
      input.value = value;
      input.checked = selectedLabels.has(value);
      const text = document.createElement("span");
      text.textContent = label;
      option.append(input, text);
      optionsContainer.append(option);
    });
    if (empty instanceof HTMLElement) {
      empty.textContent = lazyQuery ? "没有匹配的选项" : "暂无可用选项";
      empty.hidden = records.size > 0;
      optionsContainer.append(empty);
    }
    options = Array.from(optionsContainer.querySelectorAll("[data-opportunity-filter-option]"));
    updateSelection();
  };

  const lazyUrl = (page) => {
    const url = new URL(picker.dataset.opportunityFilterOptionsUrl || "", window.location.href);
    url.searchParams.set("kind", picker.dataset.opportunityFilterOptionKind || "");
    url.searchParams.set("q", lazyQuery);
    url.searchParams.set("page", String(page));
    url.searchParams.set("page_size", "40");
    const scope = picker.dataset.opportunityFilterOptionScope;
    if (scope) url.searchParams.set("scope", scope);
    inputs()
      .filter((input) => input.checked)
      .forEach((input) => url.searchParams.append("selected", input.value));
    return url;
  };

  const loadLazyOptions = async ({ reset = false } = {}) => {
    if (!(picker.dataset.opportunityFilterOptionsUrl || "")) return;
    if (lazyLoading) {
      if (reset) lazyReloadPending = true;
      return;
    }
    if (reset) lazyPage = 0;
    const page = lazyPage + 1;
    const requestId = ++lazyRequest;
    lazyLoading = true;
    picker.setAttribute("aria-busy", "true");
    if (more instanceof HTMLButtonElement) more.disabled = true;
    try {
      const response = await fetch(lazyUrl(page), {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) throw new Error(`option request failed: ${response.status}`);
      const payload = await response.json();
      if (requestId !== lazyRequest || !Array.isArray(payload.items)) return;
      renderLazyOptions(payload.items, { append: !reset && page > 1 });
      lazyPage = Number.isInteger(payload.page) ? payload.page : page;
      lazyHasMore = payload.has_next === true;
      if (more instanceof HTMLButtonElement) more.hidden = !lazyHasMore;
      if (empty instanceof HTMLElement) empty.hidden = payload.items.length > 0;
    } catch {
      if (requestId === lazyRequest && empty instanceof HTMLElement) {
        empty.hidden = false;
        empty.textContent = "选项加载失败，请重试";
      }
    } finally {
      if (requestId === lazyRequest) {
        lazyLoading = false;
        picker.removeAttribute("aria-busy");
        if (more instanceof HTMLButtonElement) more.disabled = false;
        if (lazyReloadPending) {
          lazyReloadPending = false;
          loadLazyOptions({ reset: true });
        }
      }
    }
  };

  optionsContainer.addEventListener("change", (event) => {
    const input = event.target;
    if (!(input instanceof HTMLInputElement) || input.type !== "checkbox") return;
    const option = input.closest("[data-opportunity-filter-option]");
    const label = option?.dataset.opportunityFilterLabel || "";
    if (input.checked) selectedLabels.set(input.value, label);
    else selectedLabels.delete(input.value);
    updateSelection();
  });
  search.addEventListener("input", () => {
    if (!lazy) {
      applySearch();
      return;
    }
    lazyQuery = search.value;
    window.clearTimeout(lazyTimer);
    lazyTimer = window.setTimeout(() => loadLazyOptions({ reset: true }), 220);
  });
  search.addEventListener("keydown", (event) => {
    if (event.key === "Enter") event.preventDefault();
  });
  trigger.addEventListener("click", () => {
    search.value = "";
    lazyQuery = "";
    if (!lazy) applySearch();
    dialog.showModal();
    if (lazy) loadLazyOptions({ reset: true });
    requestAnimationFrame(() => search.focus());
  });
  clear.addEventListener("click", () => {
    selectedLabels.clear();
    inputs().forEach((input) => {
      input.checked = false;
    });
    updateSelection();
    search.focus();
  });
  if (more instanceof HTMLButtonElement) {
    more.addEventListener("click", () => {
      if (lazyHasMore) loadLazyOptions();
    });
  }
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
      submitOpportunityFilter(picker.closest("form"));
    }
  });

  updateSelection();
  if (!lazy) applySearch();
}

export function initializeOpportunityFilterPickers(root = document) {
  pickerElements(root).forEach(initializePicker);
}
