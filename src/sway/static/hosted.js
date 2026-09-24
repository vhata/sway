/* One request at a time per tab. Private credentials never enter browser storage. */
(() => {
  const join = document.querySelector("#join-form");
  if (join) {
    const secret = location.hash.slice(1);
    history.replaceState(null, "", location.pathname);
    const field = join.querySelector('[name="secret"]');
    field.value = secret;
    if (!secret) {
      document.querySelector("#invite-error").textContent =
        "The private part of this invitation is missing. Ask the host for a new link.";
      join.querySelector("button").disabled = true;
    }
  }
  if (!document.querySelector("#table")) return;

  let busy = false;
  let queuedPoll = false;
  let queuedMutation = null;
  let stopped = false;
  const disabledControls = new Map();
  let timer;
  let failures = 0;
  let uncertain = null;
  const status = document.createElement("div");
  status.className = "notice";
  status.setAttribute("role", "status");
  document.querySelector("#table").before(status);

  function schedule() {
    clearTimeout(timer);
    if (stopped) return;
    const delay = failures ? Math.min(30000, 2000 * 2 ** failures) : document.hidden ? 15000 : 2000;
    timer = setTimeout(poll, delay);
  }

  function disableChoices(disabled) {
    document.documentElement.dataset.swayLocked = String(disabled);
    for (const button of document.querySelectorAll('#table button[type="submit"]')) {
      if (disabled) {
        if (!disabledControls.has(button)) disabledControls.set(button, button.disabled);
        button.disabled = true;
      } else if (disabledControls.has(button)) {
        button.disabled = disabledControls.get(button);
      }
    }
    if (!disabled) {
      disabledControls.clear();
      document.querySelector("#decision-form")?.dispatchEvent(new Event("change"));
    }
  }

  function notice(text, retry = false) {
    status.replaceChildren(document.createTextNode(text));
    if (retry) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = "Retry saved request";
      button.addEventListener("click", async () => {
        if (busy || !uncertain) return;
        // Refresh authoritative state before resolving a possibly committed request.
        await poll();
        if (!busy && !failures && uncertain) await request(uncertain);
      });
      status.append(button);
    }
  }

  function apply(html) {
    const parsed = new DOMParser().parseFromString(html, "text/html");
    const next = parsed.querySelector("#table");
    const current = document.querySelector("#table");
    if (!next || !current) return false;
    const keys = ["revision", "lobbyRevision", "preferenceVersion"];
    if (keys.some((key) => Number(next.dataset[key]) < Number(current.dataset[key]))) return true;
    const detail = {};
    document.dispatchEvent(new CustomEvent("sway:beforeSwap", { detail }));
    current.replaceWith(next);
    disabledControls.clear();
    document.dispatchEvent(new CustomEvent("sway:afterSwap"));
    if (uncertain || queuedMutation) disableChoices(true);
    return true;
  }

  async function request(pending) {
    if (busy || stopped) return;
    busy = true;
    clearTimeout(timer);
    if (pending) disableChoices(true);
    const table = document.querySelector("#table");
    if (!table) {
      busy = false;
      return;
    }
    const params = new URLSearchParams({
      revision: table.dataset.revision,
      lobby_revision: table.dataset.lobbyRevision,
      preference_version: table.dataset.preferenceVersion,
    });
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(pending?.url ?? `${table.dataset.url}/updates?${params}`, {
        method: pending ? "POST" : "GET",
        body: pending?.body,
        headers: { "HX-Request": "true" },
        credentials: "same-origin",
        cache: "no-store",
        signal: controller.signal,
      });
      if ([401, 403, 404].includes(response.status)) {
        uncertain = null;
        queuedMutation = null;
        stopped = true;
        table.replaceChildren();
        notice("Your access to this table has ended. Return to your player to sign in again.");
        const link = document.createElement("a");
        link.href = "/account";
        link.textContent = "Your player";
        status.append(link);
        return;
      }
      if (response.status === 204) {
        failures = 0;
        if (!uncertain) notice("");
        return;
      }
      if (response.ok || [409, 422].includes(response.status)) {
        const html = await response.text();
        if (pending) uncertain = null;
        if (!apply(html)) {
          throw new Error("No table in response");
        }
        failures = 0;
        if (!uncertain) notice("");
      } else {
        throw new Error("Request failed");
      }
    } catch {
      failures += 1;
      if (pending?.retryable) uncertain = pending;
      notice(
        uncertain
          ? "The connection was interrupted. Your choice may be saved. Retry the same request to check safely."
          : "Reconnecting to your table…",
        Boolean(uncertain),
      );
      disableChoices(true);
    } finally {
      clearTimeout(timeout);
      busy = false;
      if (!uncertain && !failures && !queuedMutation) disableChoices(false);
      if (!stopped && document.querySelector("#table")) {
        if (queuedMutation && !failures) {
          const next = queuedMutation;
          queuedMutation = null;
          void request(next);
          return;
        }
        schedule();
        if (queuedPoll) {
          queuedPoll = false;
          void poll();
        }
      }
    }
  }

  async function poll() {
    if (busy) {
      queuedPoll = true;
      return;
    }
    await request(null);
  }

  document.addEventListener("submit", async (event) => {
    const form = event.target;
    if (!form.closest("#table") || form.action.endsWith("/invite")) return;
    event.preventDefault();
    if (uncertain || queuedMutation || failures || stopped) return;
    const body = new URLSearchParams();
    for (const [key, value] of new FormData(form)) body.append(key, value);
    if (form.id === "decision-form") body.set("request_id", crypto.randomUUID());
    const pending = { url: form.action, body, retryable: form.id === "decision-form" };
    if (busy) {
      queuedMutation = pending;
      disableChoices(true);
    } else await request(pending);
  });
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) void poll();
    else schedule();
  });
  window.addEventListener("online", () => {
    disableChoices(true);
    void poll();
  });
  window.addEventListener("offline", () => {
    failures = 1;
    disableChoices(true);
    notice("Reconnecting to your table…");
  });
  window.addEventListener("pageshow", (event) => {
    if (event.persisted) {
      disableChoices(true);
      void poll();
    }
  });
  schedule();
})();
