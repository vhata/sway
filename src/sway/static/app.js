/* Local selection state stays in the browser until a decision is confirmed. */
(() => {
  let focusedBeforeSwap = null;
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
      for (const choice of form.querySelectorAll(".choice")) {
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
  document.addEventListener("htmx:afterSwap", () => {
    setup(document);
    const previous = focusedBeforeSwap ? document.getElementById(focusedBeforeSwap) : null;
    const target =
      previous && !previous.disabled ? previous : document.getElementById("decision-heading");
    target?.focus({ preventScroll: true });
    focusedBeforeSwap = null;
  });
  document.addEventListener("htmx:beforeSwap", (event) => {
    focusedBeforeSwap = document.activeElement?.id;
    if ([409, 422].includes(event.detail.xhr.status)) {
      event.detail.shouldSwap = true;
      event.detail.isError = false;
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
