/* Local selection state stays in the browser until a decision is confirmed. */
(() => {
  let focusedBeforeSwap = null;
  let selectionBeforeSwap = null;
  let decisionBeforeSwap = null;
  let positionBeforeSwap = null;
  let panelsBeforeSwap = null;
  let editsBeforeSwap = [];
  const focusable = "a[href], button, input, select, textarea, summary";
  // Refreshes replace the whole board or table. A control without an ID is
  // matched by its nearest keyed or identified container and by attributes
  // that stay the same between renders, never by its visible text.
  function focusKey(element) {
    const scope = element.parentElement?.closest("[data-key], [id]");
    if (!scope) return null;
    return [
      scope.dataset.key ?? `#${scope.id}`,
      element.tagName,
      element.getAttribute("type"),
      element.getAttribute("name"),
      ["checkbox", "radio"].includes(element.type) ? element.value : null,
      element.dataset.move,
      element.closest("[data-option]")?.dataset.option,
      element.getAttribute("href"),
    ].join("|");
  }
  function sameKey(key) {
    return [...document.querySelectorAll(focusable)].filter((control) => focusKey(control) === key);
  }
  function describeFocus() {
    const element = document.activeElement;
    if (!element || element === document.body) return null;
    if (element.id) return { element, id: element.id };
    const key = focusKey(element);
    return key ? { element, key, index: sameKey(key).indexOf(element) } : { element };
  }
  function findFocus(previous) {
    if (!previous) return null;
    // Focus outside the replaced region is unaffected by the swap.
    if (previous.element.isConnected) return previous.element;
    if (previous.id) return document.getElementById(previous.id);
    if (!previous.key) return null;
    const matches = sameKey(previous.key);
    return matches[previous.index] ?? matches[0] ?? null;
  }
  // A keyed form keeps the fields its user changed. Unchanged fields, hidden
  // revisions and CSRF tokens come from the refresh, so saving applies only
  // those changes to the latest server state. A checkbox or radio group is one
  // field: any change keeps the user's whole selection. The form whose
  // submission succeeded shows the server's result instead; a rejected or
  // conflicting submission keeps the edits for another attempt.
  function unsavedEdits(saved) {
    const edits = [];
    for (const form of document.querySelectorAll("form[data-key]")) {
      if (saved && form.dataset.key === saved) continue;
      const groups = new Map();
      for (const control of form.querySelectorAll("input[name], select[name], textarea[name]")) {
        if (["hidden", "submit", "button", "reset", "file"].includes(control.type)) continue;
        const edit = { form: form.dataset.key, name: control.name };
        if (["checkbox", "radio"].includes(control.type)) {
          const group = groups.get(control.name) ?? { ...edit, checked: [], changed: false };
          if (control.checked) group.checked.push(control.value);
          group.changed ||= control.checked !== control.defaultChecked;
          groups.set(control.name, group);
        } else if (control.tagName === "SELECT") {
          const initial = Math.max(
            0,
            [...control.options].findIndex((option) => option.defaultSelected),
          );
          if (control.selectedIndex !== initial) edits.push({ ...edit, value: control.value });
        } else if (control.value !== control.defaultValue) {
          edits.push({ ...edit, value: control.value });
        }
      }
      edits.push(...[...groups.values()].filter((group) => group.changed));
    }
    return edits;
  }
  function restoreEdits(edits) {
    for (const edit of edits) {
      const form = document.querySelector(`form[data-key="${CSS.escape(edit.form)}"]`);
      const controls = [...(form?.elements ?? [])].filter((element) => element.name === edit.name);
      if (edit.checked) {
        for (const control of controls) control.checked = edit.checked.includes(control.value);
        continue;
      }
      const control = controls[0];
      if (
        control &&
        (control.tagName !== "SELECT" ||
          [...control.options].some((option) => option.value === edit.value))
      ) {
        control.value = edit.value;
      }
    }
  }
  function decisionIdentity() {
    return (
      document.querySelector("#decision-form")?.dataset.decision ??
      (document.querySelector(".finished") ? "finished" : "opponents")
    );
  }
  function setup(root) {
    const players = root.querySelector("#players");
    const supply = root.querySelector("#supply-mode");
    const updateSetup = () => {
      if (players) {
        for (const row of root.querySelectorAll("[data-opponent]")) {
          row.hidden = Number(row.dataset.opponent) >= Number(players.value);
        }
      }
      const manual = root.querySelector("#manual-supply");
      if (manual && supply) manual.hidden = supply.value !== "manual";
    };
    players?.addEventListener("change", updateSetup);
    supply?.addEventListener("change", updateSetup);
    updateSetup();

    const form = root.querySelector("#decision-form");
    if (!form) return;
    const updateSelection = () => {
      if (form.dataset.ordered === "true") return;
      const selected = form.querySelectorAll('input[name="choices"]:checked');
      const minimum = Number(form.dataset.minimum);
      const maximum = Number(form.dataset.maximum);
      const confirm = form.querySelector('[type="submit"]');
      if (confirm) {
        confirm.disabled =
          document.documentElement.dataset.swayLocked === "true" ||
          selected.length < minimum ||
          selected.length > maximum;
      }
      for (const choice of form.querySelectorAll(".choice, .order-item")) {
        choice.classList.toggle("selected", Boolean(choice.querySelector("input:checked")));
      }
      const status = form.querySelector(".selection-status");
      if (status) status.textContent = `${selected.length} selected`;
    };
    form.addEventListener("change", updateSelection);
    form.addEventListener("reset", () => setTimeout(updateSelection, 0));
    form.addEventListener("click", (event) => {
      const mover = event.target.closest("[data-move]");
      if (!mover) return;
      const item = mover.closest(".order-item");
      const sibling =
        mover.dataset.move === "up" ? item.previousElementSibling : item.nextElementSibling;
      if (!sibling) return;
      if (mover.dataset.move === "up") item.parentNode.insertBefore(item, sibling);
      else item.parentNode.insertBefore(sibling, item);
      mover.focus();
    });
    updateSelection();
  }

  document.addEventListener("DOMContentLoaded", () => setup(document));
  function afterSwap() {
    const form = document.querySelector("#decision-form");
    if (form && selectionBeforeSwap?.id === form.dataset.decision) {
      const controls = new Map(
        [...form.querySelectorAll('input[name="choices"]')].map((input) => [input.value, input]),
      );
      const rows = new Map(
        [...form.querySelectorAll(".order-item")].map((row) => [row.dataset.option, row]),
      );
      for (const previous of selectionBeforeSwap.choices) {
        const control = controls.get(previous.value);
        if (control && control.type !== "hidden") control.checked = previous.checked;
        const row = rows.get(previous.value);
        if (row) row.parentElement.appendChild(row);
      }
    }
    selectionBeforeSwap = null;
    for (const panel of document.querySelectorAll("details[data-key]")) {
      const open = panelsBeforeSwap?.get(panel.dataset.key);
      if (open !== undefined) panel.open = open;
    }
    panelsBeforeSwap = null;
    restoreEdits(editsBeforeSwap);
    editsBeforeSwap = [];
    setup(document);
    const previous = findFocus(focusedBeforeSwap);
    const changed = decisionBeforeSwap !== decisionIdentity();
    const heading = document.querySelector("#decision-heading, #result-heading, #opponent-heading");
    const target = changed ? heading : previous && !previous.disabled ? previous : heading;
    const position = positionBeforeSwap;
    // Run after layout changes so replacing a tall choice list cannot leave
    // the player below the next decision. No animated scrolling is needed.
    requestAnimationFrame(() => {
      target?.focus({ preventScroll: true });
      if (changed) heading?.scrollIntoView({ block: "start", behavior: "instant" });
      else if (position) window.scrollTo({ ...position, behavior: "instant" });
    });
    focusedBeforeSwap = null;
    decisionBeforeSwap = null;
    positionBeforeSwap = null;
  }
  document.addEventListener("htmx:afterSwap", afterSwap);
  document.addEventListener("sway:afterSwap", afterSwap);
  function beforeSwap(event) {
    focusedBeforeSwap = describeFocus();
    panelsBeforeSwap = new Map(
      [...document.querySelectorAll("details[data-key]")].map((panel) => [
        panel.dataset.key,
        panel.open,
      ]),
    );
    const source = event.detail.requestConfig?.elt ?? event.detail.source;
    const status = event.detail.xhr?.status ?? event.detail.status;
    editsBeforeSwap = unsavedEdits(status >= 200 && status < 300 ? source?.dataset?.key : null);
    decisionBeforeSwap = decisionIdentity();
    positionBeforeSwap = { left: window.scrollX, top: window.scrollY };
    const form = document.querySelector("#decision-form");
    selectionBeforeSwap = form
      ? {
          id: form.dataset.decision,
          choices: [...form.querySelectorAll('input[name="choices"]')].map((input) => ({
            value: input.value,
            checked: input.checked,
          })),
        }
      : null;
    if ([409, 422].includes(event.detail.xhr?.status)) {
      event.detail.shouldSwap = true;
      event.detail.isError = false;
    }
  }
  document.addEventListener("htmx:beforeSwap", beforeSwap);
  document.addEventListener("sway:beforeSwap", beforeSwap);
  document.addEventListener("htmx:responseError", (event) => {
    const panel = document.querySelector(".decision-panel");
    if (panel) {
      const notice = document.createElement("p");
      notice.className = "notice error";
      notice.setAttribute("role", "alert");
      notice.textContent =
        event.detail.xhr.status === 403
          ? "This form has expired. Reload the page before making another choice."
          : "This move could not be saved. Reload your table to see the latest saved game.";
      panel.prepend(notice);
    }
  });
  document.addEventListener("htmx:sendError", () => {
    const panel = document.querySelector(".decision-panel");
    if (panel) {
      const notice = document.createElement("p");
      notice.className = "notice error";
      notice.setAttribute("role", "alert");
      notice.textContent =
        "The connection was interrupted. Reload to see your saved game, then try again.";
      panel.prepend(notice);
    }
  });
})();
