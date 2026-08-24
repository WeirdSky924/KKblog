function bindRecordBatch(root) {
  const form = root.querySelector?.("[data-record-batch-form]");
  if (!(form instanceof HTMLFormElement) || form.dataset.recordsBound === "true") return;
  form.dataset.recordsBound = "true";
  const selections = [...form.querySelectorAll("[data-record-select]")];
  const count = form.querySelector("[data-record-selected-count]");
  const submit = form.querySelector("[data-record-batch-delete]");
  const update = () => {
    const selected = selections.filter((input) => input.checked).length;
    if (count instanceof HTMLInputElement) count.value = String(selected);
    if (submit instanceof HTMLButtonElement) {
      submit.disabled = selected === 0;
      submit.querySelector("span")?.replaceChildren(`删除已选记录（${selected}）`);
    }
  };
  selections.forEach((input) => input.addEventListener("change", update));
  form.addEventListener("formdata", (event) => {
    const active = document.activeElement;
    if (active instanceof HTMLButtonElement && active.dataset.singleDeleteVersion) {
      event.formData.set("single_expected_version", active.dataset.singleDeleteVersion);
      event.formData.set("expected_count", "1");
    }
  });
  update();
}

export function initializeRecords(root = document) {
  bindRecordBatch(root);
}
