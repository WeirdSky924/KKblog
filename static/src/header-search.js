const SEARCH_DEBOUNCE_MS = 180;

function sameOriginPath(value) {
  try {
    const url = new URL(value, window.location.origin);
    if (url.origin !== window.location.origin) return "";
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return "";
  }
}

function searchForms(scope) {
  const forms = [];
  if (scope instanceof HTMLFormElement && scope.matches("[data-header-search]")) {
    forms.push(scope);
  }
  scope.querySelectorAll?.("form[data-header-search]").forEach((form) =>
    forms.push(form),
  );
  return forms;
}

function initializeHeaderSearchForm(form) {
  if (form.dataset.headerSearchBound === "true") return;
  const type = form.querySelector("[data-header-search-type]");
  const input = form.querySelector("[data-header-search-query]");
  if (!(type instanceof HTMLSelectElement) || !(input instanceof HTMLInputElement)) {
    return;
  }
  form.dataset.headerSearchBound = "true";
  const endpoint = form.dataset.searchSuggestionsUrl || "";
  const panel = form.querySelector("[data-header-search-suggestions]");
  const list = form.querySelector("[data-header-search-suggestion-list]");
  const status = form.querySelector("[data-header-search-status]");
  const suggestionsEnabled =
    endpoint &&
    panel instanceof HTMLElement &&
    list instanceof HTMLElement &&
    status instanceof HTMLElement;
  let timer = 0;
  let request = null;
  let activeIndex = -1;

  const options = () => Array.from(list?.querySelectorAll("[role='option']") || []);

  const close = () => {
    if (panel instanceof HTMLElement) panel.hidden = true;
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
    activeIndex = -1;
    options().forEach((option) => option.setAttribute("aria-selected", "false"));
  };

  const clear = () => {
    request?.abort();
    request = null;
    window.clearTimeout(timer);
    if (list instanceof HTMLElement) list.replaceChildren();
    if (status instanceof HTMLElement) status.replaceChildren();
    delete form.dataset.searchState;
    close();
  };

  const openWithStatus = (message, state) => {
    if (!suggestionsEnabled) return;
    list.replaceChildren();
    status.textContent = message;
    form.dataset.searchState = state;
    panel.hidden = false;
    input.setAttribute("aria-expanded", "true");
  };

  const setActive = (index) => {
    const items = options();
    if (!items.length) return;
    activeIndex = (index + items.length) % items.length;
    items.forEach((item, itemIndex) => {
      item.setAttribute("aria-selected", String(itemIndex === activeIndex));
    });
    input.setAttribute("aria-activedescendant", items[activeIndex].id);
    items[activeIndex].scrollIntoView({ block: "nearest" });
  };

  const suggestionNode = (item, index) => {
    const path = sameOriginPath(item?.url || "");
    if (!path || typeof item?.label !== "string") return null;
    const link = document.createElement("a");
    link.className = "header-search__suggestion";
    link.href = path;
    link.id = `header-search-option-${index}`;
    link.setAttribute("role", "option");
    link.setAttribute("aria-selected", "false");

    const isAuthor = type.value === "author";
    if (isAuthor) {
      const avatar = document.createElement("span");
      avatar.className = "header-search__suggestion-avatar";
      const imagePath = sameOriginPath(item.image_url || "");
      if (imagePath) {
        const image = document.createElement("img");
        image.src = imagePath;
        image.alt = "";
        image.width = 40;
        image.height = 40;
        avatar.append(image);
      } else {
        avatar.textContent = item.initial || item.label[0];
      }
      link.append(avatar);
    } else {
      link.classList.add("header-search__suggestion--article");
    }

    const copy = document.createElement("span");
    copy.className = "header-search__suggestion-copy";
    const label = document.createElement("strong");
    label.textContent = item.label;
    const meta = document.createElement("span");
    meta.className = "header-search__suggestion-meta";
    const metadata = [item.description];
    if (!isAuthor) {
      metadata.push(item.section);
      if (Array.isArray(item.tags)) {
        metadata.push(...item.tags.map((tag) => `#${tag}`));
      }
    }
    metadata.filter(Boolean).forEach((value) => {
      const entry = document.createElement("span");
      entry.textContent = value;
      meta.append(entry);
    });
    copy.append(label, meta);
    link.append(copy);
    link.addEventListener("pointerenter", () => setActive(index));
    return link;
  };

  const render = (items) => {
    list.replaceChildren();
    const nodes = Array.isArray(items)
      ? items.slice(0, 5).map(suggestionNode).filter(Boolean)
      : [];
    if (!nodes.length) {
      openWithStatus(
        `没有匹配的${type.value === "author" ? "作者" : "文章"}。`,
        "empty",
      );
      return;
    }
    list.append(...nodes);
    status.textContent = `${nodes.length} 条建议`;
    form.dataset.searchState = "ready";
    panel.hidden = false;
    input.setAttribute("aria-expanded", "true");
    activeIndex = -1;
  };

  const load = async () => {
    const query = input.value.trim();
    if (!query) {
      clear();
      return;
    }
    request?.abort();
    request = new AbortController();
    openWithStatus("正在搜索…", "loading");
    const url = new URL(endpoint, window.location.origin);
    url.searchParams.set("type", type.value);
    url.searchParams.set("q", query);
    try {
      const response = await fetch(url, {
        credentials: "same-origin",
        headers: { "X-Requested-With": "XMLHttpRequest" },
        signal: request.signal,
      });
      if (!response.ok) throw new Error("suggestion request failed");
      const payload = await response.json();
      if (input.value.trim() === query) render(payload.items);
    } catch (error) {
      if (error.name !== "AbortError") {
        openWithStatus("暂时无法获取建议。", "error");
      }
    }
  };

  const schedule = () => {
    if (!suggestionsEnabled) return;
    window.clearTimeout(timer);
    timer = window.setTimeout(load, SEARCH_DEBOUNCE_MS);
  };

  const updateType = () => {
    input.placeholder = type.value === "author" ? "搜索作者" : "搜索文章标题";
    clear();
    if (input.value.trim()) schedule();
  };

  type.addEventListener("change", updateType);
  if (!suggestionsEnabled) return;
  input.addEventListener("input", (event) => {
    if (!event.isComposing) schedule();
  });
  input.addEventListener("compositionend", schedule);
  input.addEventListener("focus", () => {
    if (options().length) {
      panel.hidden = false;
      input.setAttribute("aria-expanded", "true");
    } else if (input.value.trim()) {
      schedule();
    }
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown") {
      if (options().length) {
        event.preventDefault();
        setActive(activeIndex + 1);
      }
    } else if (event.key === "ArrowUp") {
      if (options().length) {
        event.preventDefault();
        setActive(activeIndex - 1);
      }
    } else if (event.key === "Enter" && activeIndex >= 0) {
      event.preventDefault();
      options()[activeIndex]?.click();
    } else if (event.key === "Escape") {
      event.preventDefault();
      close();
    }
  });
  form.addEventListener("focusout", () => {
    window.setTimeout(() => {
      if (!form.contains(document.activeElement)) close();
    });
  });
}

export function initializeHeaderSearch(scope = document) {
  searchForms(scope).forEach(initializeHeaderSearchForm);
}
