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

async function saveForm(form) {
  if (form.dataset.saving === "true") return;
  form.dataset.saving = "true";
  form.setAttribute("aria-busy", "true");
  try {
    const response = await fetch(form.action, {
      method: "POST",
      body: new FormData(form),
      credentials: "same-origin",
      headers: { "X-CSRFToken": csrfToken(), "X-Requested-With": "XMLHttpRequest" },
    });
    if (!response.ok) {
      setStatus(form, "答案保存失败，请重试。", true);
      return;
    }
    updateSaveContract(form, response);
    setStatus(form, "答案已自动保存。", false);
  } catch {
    setStatus(form, "答案保存失败，请检查网络后重试。", true);
  } finally {
    delete form.dataset.saving;
    form.removeAttribute("aria-busy");
  }
}

function bindForm(form) {
  if (!(form instanceof HTMLFormElement) || form.dataset.quizBound === "true") return;
  form.dataset.quizBound = "true";
  form.dataset.quizAnswered = String(formHasAnswer(form));
  let timer = 0;
  const schedule = () => {
    updateProgress(form);
    window.clearTimeout(timer);
    const delay = form.querySelector("textarea") ? 550 : 0;
    timer = window.setTimeout(() => saveForm(form), delay);
  };
  form.querySelectorAll("input[type=radio], input[type=checkbox]").forEach((input) => {
    input.addEventListener("change", schedule);
  });
  form.querySelector("textarea")?.addEventListener("input", schedule);
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

export function initializeQuiz(root = document) {
  const forms = [];
  if (root instanceof HTMLFormElement && root.matches("[data-quiz-save]")) forms.push(root);
  root.querySelectorAll?.("form[data-quiz-save]").forEach((form) => forms.push(form));
  forms.forEach(bindForm);
  bindTimer(root);
}
