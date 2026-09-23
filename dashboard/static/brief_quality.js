(() => {
  const root = document.querySelector("[data-review-session]");
  if (!root || root.dataset.reviewOpen !== "True") return;
  let activeSeconds = 0;
  const isActive = () => document.visibilityState === "visible" && document.hasFocus();
  const sample = () => { if (isActive()) activeSeconds += 1; };
  const flush = () => {
    const seconds = Math.min(30, activeSeconds);
    if (seconds < 1) return;
    activeSeconds -= seconds;
    const body = new FormData();
    body.set("client_event_id", crypto.randomUUID());
    body.set("active_seconds", String(seconds));
    fetch(`/internal/brief-review-sessions/${root.dataset.reviewSession}/activity-pulses`, {
      method: "POST", body, credentials: "same-origin", keepalive: true,
    }).catch(() => { activeSeconds += seconds; });
  };
  setInterval(sample, 1000);
  setInterval(flush, 15000);
  ["blur", "pagehide"].forEach((name) => addEventListener(name, flush));
  document.addEventListener("visibilitychange", () => { if (document.hidden) flush(); });
  document.addEventListener("submit", flush);
})();
