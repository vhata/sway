/* Local selection state stays in the browser until a decision is confirmed. */
(() => {
  let focusedBeforeSwap = null;
  let selectionBeforeSwap = null;
  let decisionBeforeSwap = null;
  let positionBeforeSwap = null;
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
        confirm.disabled = selected.length < minimum || selected.length > maximum;
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
    setup(document);
    const previous = focusedBeforeSwap ? document.getElementById(focusedBeforeSwap) : null;
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
    focusedBeforeSwap = document.activeElement?.id;
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
