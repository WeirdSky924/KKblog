function csrfToken() {
  const match = document.cookie.match(/(?:^|; )(?:kaj_csrf|csrftoken)=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

function setStatus(form, message, error = false) {
  const root = form.closest("[data-quiz-attempt]") ?? document;
  const status = root.querySelector("[data-quiz-status]");
  if (!(status instanceof HTMLElement)) return;
  status.textContent = message;
  status.dataset.level = error ? "error" : "success";
}

function nextRequestId() {
  if (typeof globalThis.crypto?.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

const pendingQuizSaves = new WeakMap();

function updateSaveContract(form, response) {
  const version = response.headers.get("X-Quiz-Response-Version");
  const expectedVersion = form.elements.namedItem("expected_version");
  const requestId = form.elements.namedItem("request_id");
  if (version && expectedVersion instanceof HTMLInputElement) {
    expectedVersion.value = version;
  }
  if (requestId instanceof HTMLInputElement) {
    requestId.value = nextRequestId();
  }
}

function formHasAnswer(form) {
  const textarea = form.querySelector("textarea");
  if (textarea instanceof HTMLTextAreaElement) return textarea.value.trim().length > 0;
  return form.querySelectorAll("input[type=radio]:checked, input[type=checkbox]:checked").length > 0;
}

function updateProgress(form) {
  const root = form.closest("[data-quiz-attempt]");
  const progress = root?.querySelector("[data-quiz-progress]");
  if (!(progress instanceof HTMLElement)) return;
  const answeredBefore = form.dataset.quizAnswered === "true";
  const answeredNow = formHasAnswer(form);
  if (answeredBefore === answeredNow) return;
  const total = Number(progress.dataset.total || 0);
  const answered = Math.max(
    0,
    Math.min(total, Number(progress.dataset.answered || 0) + (answeredNow ? 1 : -1)),
  );
  progress.dataset.answered = String(answered);
  form.dataset.quizAnswered = String(answeredNow);
  const bar = progress.querySelector("[data-quiz-progress-bar]");
  const label = progress.querySelector("[data-quiz-progress-label]");
  if (bar instanceof HTMLElement) {
    bar.style.setProperty("--quiz-progress", `${total ? (answered / total) * 100 : 0}%`);
  }
  if (label instanceof HTMLElement) label.textContent = `${answered} / ${total}`;
}

function quizAttemptRoot(root) {
  if (root instanceof HTMLElement && root.matches("[data-quiz-attempt]")) {
    return root;
  }
  if (root instanceof HTMLElement) {
    const ancestor = root.closest("[data-quiz-attempt]");
    if (ancestor instanceof HTMLElement) return ancestor;
  }
  const attempt = root.querySelector?.("[data-quiz-attempt]");
  return attempt instanceof HTMLElement ? attempt : null;
}

function quizResponses(root) {
  return Array.from(root.querySelectorAll("[data-quiz-response]")).sort(
    (left, right) =>
      Number(left.dataset.quizPosition || 0) -
      Number(right.dataset.quizPosition || 0),
  );
}

function syncPracticeSubmitControl(root, response) {
  const button = root.querySelector("[data-quiz-practice-submit]");
  if (!(button instanceof HTMLButtonElement)) return;
  const responses = quizResponses(root);
  const attemptFormId = button.dataset.quizAttemptForm;
  const allResponsesRevealed =
    responses.length > 0 &&
    responses.every((item) => item.dataset.quizRevealed === "true");
  const label = button.querySelector("span");
  if (attemptFormId && allResponsesRevealed) {
    button.disabled = false;
    button.removeAttribute("aria-disabled");
    button.setAttribute("form", attemptFormId);
    button.removeAttribute("formaction");
    button.removeAttribute("data-quiz-submit-response");
    button.setAttribute("data-quiz-submit-attempt", "");
    if (label instanceof HTMLElement) {
      label.textContent = button.dataset.quizAttemptLabel || "提交整张试卷";
    }
    return;
  }
  const form = response?.querySelector("form[data-quiz-save]");
  const revealed = response?.dataset.quizRevealed === "true";
  if (!(form instanceof HTMLFormElement) || !form.id || revealed) {
    button.disabled = true;
    button.setAttribute("aria-disabled", "true");
    button.removeAttribute("form");
    button.removeAttribute("formaction");
    button.removeAttribute("data-quiz-submit-response");
    button.removeAttribute("data-quiz-submit-attempt");
    if (label instanceof HTMLElement) {
      label.textContent = button.dataset.quizResponseLabel || "提交本题并查看解析";
    }
    return;
  }
  button.disabled = false;
  button.removeAttribute("aria-disabled");
  button.setAttribute("form", form.id);
  button.setAttribute("formaction", form.dataset.quizSubmitAction || "");
  button.removeAttribute("data-quiz-submit-attempt");
  button.setAttribute("data-quiz-submit-response", "");
  if (label instanceof HTMLElement) {
    label.textContent = button.dataset.quizResponseLabel || "提交本题并查看解析";
  }
}

function syncExplanationPanel(root, response) {
  const panel = root.querySelector("[data-quiz-explanation-panel]");
  if (!(panel instanceof HTMLElement)) return;
  const workspace = panel.closest(".quiz-attempt__workspace");
  if (!(workspace instanceof HTMLElement)) return;
  const revealed =
    root.dataset.quizSubmitted === "true" ||
    response?.dataset.quizRevealed === "true";
  workspace.classList.toggle("quiz-attempt__workspace--has-explanations", revealed);
  panel.setAttribute("aria-hidden", String(!revealed));
  panel.toggleAttribute("inert", !revealed);
}

function quizPositionKey(root) {
  const attemptId = root.dataset.quizAttemptId;
  return attemptId ? `kaj:quiz:${attemptId}:position` : "";
}

function storedQuizPosition(root, responses) {
  const key = quizPositionKey(root);
  if (!key) return 1;
  try {
    const value = Number.parseInt(window.sessionStorage.getItem(key) || "", 10);
    if (
      Number.isInteger(value) &&
      responses.some((response) => Number(response.dataset.quizPosition) === value)
    ) {
      return value;
    }
  } catch {
    // Session storage can be unavailable in private browsing contexts.
  }
  return Number(responses[0]?.dataset.quizPosition || 1);
}

function persistQuizPosition(root, position) {
  const key = quizPositionKey(root);
  if (!key) return;
  try {
    window.sessionStorage.setItem(key, String(position));
  } catch {
    // The current question still works when storage is unavailable.
  }
}

function setCurrentQuizQuestion(root, position, { focus = true } = {}) {
  const responses = quizResponses(root);
  if (!responses.length) return;
  const targetIndex = Math.max(
    0,
    responses.findIndex(
      (response) => Number(response.dataset.quizPosition) === Number(position),
    ),
  );
  const target = responses[targetIndex];
  const targetPosition = Number(target.dataset.quizPosition || targetIndex + 1);
  responses.forEach((response, index) => {
    response.hidden = index !== targetIndex;
    response.dataset.quizCurrent = String(index === targetIndex);
  });

  const navItems = root.querySelectorAll("[data-quiz-question-nav]");
  navItems.forEach((item) => {
    const current = Number(item.dataset.quizPosition) === targetPosition;
    item.toggleAttribute("aria-current", current);
    if (current) item.setAttribute("aria-current", "step");
  });
  const previous = root.querySelector("[data-quiz-previous]");
  const next = root.querySelector("[data-quiz-next]");
  if (previous instanceof HTMLButtonElement) previous.disabled = targetIndex === 0;
  if (next instanceof HTMLButtonElement) {
    next.disabled = targetIndex === responses.length - 1;
  }
  root
    .querySelectorAll(
      "[data-quiz-current-label], [data-quiz-position-label], [data-quiz-explanation-current]",
    )
    .forEach((label) => {
      if (label instanceof HTMLElement) {
        label.textContent = `第 ${targetPosition} / ${responses.length} 题`;
      }
    });
  root.querySelectorAll("[data-quiz-explanation]").forEach((panel) => {
    panel.hidden = Number(panel.dataset.quizPosition) !== targetPosition;
  });
  syncPracticeSubmitControl(root, target);
  syncExplanationPanel(root, target);
  root.dataset.quizCurrentPosition = String(targetPosition);
  persistQuizPosition(root, targetPosition);
  if (focus) {
    responses[targetIndex]
      .querySelector("h2")
      ?.focus({ preventScroll: true });
  }
}

function updateQuestionNavigationState(root) {
  if (!(root instanceof HTMLElement) || root.dataset.quizSubmitted === "true") {
    return;
  }
  root.querySelectorAll("[data-quiz-question-nav]").forEach((item) => {
    const position = Number(item.dataset.quizPosition);
    const response = root.querySelector(
      `[data-quiz-response][data-quiz-position="${position}"]`,
    );
    if (response?.dataset.quizRevealed === "true") return;
    const form = response?.querySelector("form[data-quiz-save]");
    const answered = form instanceof HTMLFormElement && formHasAnswer(form);
    item.dataset.quizState = answered ? "answered" : "";
    item.classList.toggle("quiz-question-nav__item--answered", answered);
  });
}

function bindQuestionNavigation(root) {
  const attempt = quizAttemptRoot(root);
  if (!(attempt instanceof HTMLElement) || attempt.dataset.quizNavigationBound === "true") {
    return;
  }
  attempt.dataset.quizNavigationBound = "true";
  const responses = quizResponses(attempt);
  if (!responses.length) return;
  updateQuestionNavigationState(attempt);
  setCurrentQuizQuestion(attempt, storedQuizPosition(attempt, responses), {
    focus: false,
  });
  attempt.querySelectorAll("[data-quiz-question-nav]").forEach((item) => {
    item.addEventListener("click", () => {
      setCurrentQuizQuestion(attempt, item.dataset.quizPosition);
    });
  });
  attempt.querySelector("[data-quiz-previous]")?.addEventListener("click", () => {
    const current = responses.findIndex(
      (response) =>
        Number(response.dataset.quizPosition) ===
        Number(attempt.dataset.quizCurrentPosition),
    );
    if (current > 0) {
      setCurrentQuizQuestion(attempt, responses[current - 1].dataset.quizPosition);
    }
  });
  attempt.querySelector("[data-quiz-next]")?.addEventListener("click", () => {
    const current = responses.findIndex(
      (response) =>
        Number(response.dataset.quizPosition) ===
        Number(attempt.dataset.quizCurrentPosition),
    );
    if (current >= 0 && current < responses.length - 1) {
      setCurrentQuizQuestion(attempt, responses[current + 1].dataset.quizPosition);
    }
  });
}

async function saveForm(form) {
  const existing = pendingQuizSaves.get(form);
  if (existing) return existing;
  form.dataset.saving = "true";
  form.setAttribute("aria-busy", "true");
  const saving = (async () => {
    try {
      const response = await fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        credentials: "same-origin",
        headers: { "X-CSRFToken": csrfToken(), "X-Requested-With": "XMLHttpRequest" },
      });
      if (!response.ok) {
        setStatus(form, "答案保存失败，请重试。", true);
        return false;
      }
      updateSaveContract(form, response);
      setStatus(form, "答案已自动保存。", false);
      return true;
    } catch {
      setStatus(form, "答案保存失败，请检查网络后重试。", true);
      return false;
    } finally {
      delete form.dataset.saving;
      form.removeAttribute("aria-busy");
    }
  })();
  pendingQuizSaves.set(form, saving);
  try {
    return await saving;
  } finally {
    if (pendingQuizSaves.get(form) === saving) pendingQuizSaves.delete(form);
  }
}

function bindForm(form) {
  if (!(form instanceof HTMLFormElement) || form.dataset.quizBound === "true") return;
  form.dataset.quizBound = "true";
  form.dataset.quizAnswered = String(formHasAnswer(form));
  let timer = 0;
  const schedule = () => {
    updateProgress(form);
    updateQuestionNavigationState(form.closest("[data-quiz-attempt]"));
    window.clearTimeout(timer);
    const delay = form.querySelector("textarea") ? 550 : 0;
    timer = window.setTimeout(() => saveForm(form), delay);
  };
  form.querySelectorAll("input[type=radio], input[type=checkbox]").forEach((input) => {
    input.addEventListener("change", schedule);
  });
  form.querySelector("textarea")?.addEventListener("input", schedule);
  form.addEventListener("submit", (event) => {
    const button = event.submitter;
    if (!(button instanceof HTMLButtonElement) || !button.matches("[data-quiz-submit-response]")) {
      return;
    }
    if (form.dataset.quizSubmitting === "true") return;
    event.preventDefault();
    if (form.dataset.quizSubmitPending === "true") return;
    form.dataset.quizSubmitPending = "true";
    button.setAttribute("aria-disabled", "true");
    window.clearTimeout(timer);
    void (async () => {
      const pending = pendingQuizSaves.get(form);
      if (pending && !(await pending)) {
        setStatus(form, "自动保存未完成，请检查网络或刷新答案后重试。", true);
        delete form.dataset.quizSubmitPending;
        button.removeAttribute("aria-disabled");
        return;
      }
      // Let the original submit algorithm finish before calling requestSubmit again.
      await new Promise((resolve) => window.setTimeout(resolve, 0));
      delete form.dataset.quizSubmitPending;
      form.dataset.quizSubmitting = "true";
      button.removeAttribute("aria-disabled");
      form.requestSubmit(button);
    })();
  });
}

function bindTimer(root) {
  const timerElement = root.querySelector?.("[data-quiz-timer]");
  if (!(timerElement instanceof HTMLElement)) return;
  if (timerElement.dataset.quizTimerBound === "true") return;
  timerElement.dataset.quizTimerBound = "true";
  const deadline = Date.parse(timerElement.dataset.deadline || "");
  if (!Number.isFinite(deadline)) return;
  const tick = () => {
    const remaining = Math.ceil((deadline - Date.now()) / 1000);
    if (remaining <= 0) {
      timerElement.textContent = "已超过软提醒时间，仍可继续答题";
      timerElement.dataset.expired = "true";
      return;
    }
    const minutes = Math.floor(remaining / 60);
    const seconds = String(remaining % 60).padStart(2, "0");
    timerElement.textContent = `剩余 ${minutes}:${seconds}`;
    window.setTimeout(tick, 1000);
  };
  tick();
}

let quizPickerBound = false;
let quizPickerAnimationTimer = 0;

function quizPickerTrigger(event) {
  const element = event.detail?.elt;
  return element instanceof Element
    ? element.closest("[data-quiz-config-trigger]")
    : null;
}

function quizPickerLayout(trigger) {
  return trigger?.closest("[data-quiz-picker-layout]") ?? null;
}

function setQuizPickerSelection(layout, bankId) {
  if (!(layout instanceof HTMLElement) || !bankId) return;
  layout.querySelectorAll(".quiz-bank-row[data-quiz-bank-id]").forEach((row) => {
    row.classList.toggle("quiz-bank-row--selected", row.dataset.quizBankId === bankId);
  });
}

function restoreQuizPickerLayout(layout) {
  if (!(layout instanceof HTMLElement)) return;
  layout.classList.remove("quiz-picker-layout--configuring");
  if (layout.dataset.quizPickerWasSolo === "true") {
    layout.classList.add("quiz-picker-layout--solo");
  }
  delete layout.dataset.quizPickerPendingBankId;
  delete layout.dataset.quizPickerPreviousBankId;
  delete layout.dataset.quizPickerWasSolo;
}

function bindQuizPicker() {
  if (quizPickerBound) return;
  quizPickerBound = true;
  document.addEventListener("htmx:beforeRequest", (event) => {
    const trigger = quizPickerTrigger(event);
    const layout = quizPickerLayout(trigger);
    if (!(trigger instanceof HTMLElement) || !(layout instanceof HTMLElement)) return;
    layout.dataset.quizPickerWasSolo = String(
      layout.classList.contains("quiz-picker-layout--solo"),
    );
    layout.dataset.quizPickerPendingBankId = trigger.dataset.quizBankId || "";
    layout.dataset.quizPickerPreviousBankId =
      layout.querySelector(".quiz-bank-row--selected")?.dataset.quizBankId || "";
    layout.classList.remove("quiz-picker-layout--solo");
    layout.classList.add("quiz-picker-layout--configuring");
  });
  document.addEventListener("htmx:afterRequest", (event) => {
    const trigger = quizPickerTrigger(event);
    const layout = quizPickerLayout(trigger);
    if (!(trigger instanceof HTMLElement) || !(layout instanceof HTMLElement)) return;
    if (event.detail?.successful === true) return;
    const previousBankId = layout.dataset.quizPickerPreviousBankId || "";
    restoreQuizPickerLayout(layout);
    setQuizPickerSelection(layout, previousBankId);
  });
  document.addEventListener("htmx:beforeSwap", (event) => {
    const trigger = quizPickerTrigger(event);
    const layout = quizPickerLayout(trigger);
    if (!(trigger instanceof HTMLElement) || !(layout instanceof HTMLElement)) return;
    if (event.detail?.xhr?.status >= 400) {
      restoreQuizPickerLayout(layout);
    }
  });
  document.addEventListener("htmx:afterSettle", (event) => {
    const target = event.detail?.target;
    if (!(target instanceof Element) || target.id !== "quiz-config") return;
    const layout = target.closest("[data-quiz-picker-layout]");
    if (!(layout instanceof HTMLElement)) return;
    setQuizPickerSelection(layout, layout.dataset.quizPickerPendingBankId || "");
    window.clearTimeout(quizPickerAnimationTimer);
    quizPickerAnimationTimer = window.setTimeout(() => {
      layout.classList.remove("quiz-picker-layout--configuring");
      delete layout.dataset.quizPickerPendingBankId;
      delete layout.dataset.quizPickerPreviousBankId;
      delete layout.dataset.quizPickerWasSolo;
    }, 380);
  });
}

export function initializeQuiz(root = document) {
  bindQuizPicker();
  const forms = [];
  if (root instanceof HTMLFormElement && root.matches("[data-quiz-save]")) forms.push(root);
  root.querySelectorAll?.("form[data-quiz-save]").forEach((form) => forms.push(form));
  forms.forEach(bindForm);
  bindQuestionNavigation(root);
  bindTimer(root);
}
