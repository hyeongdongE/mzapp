(() => {
  const root = document.querySelector("[data-review-session]");
  if (!root || root.dataset.reviewOpen !== "True") return;
  let activeSeconds = 0;
  let sending = false;
  const storageKey = `brief-quality-pulse-${root.dataset.reviewSession}`;
  let pendingPulse = null;
  try { pendingPulse = JSON.parse(sessionStorage.getItem(storageKey)); } catch (_) {}
  const isActive = () => document.visibilityState === "visible" && document.hasFocus();
  const sample = () => { if (isActive()) activeSeconds += 1; };
  const flush = () => {
    if (sending) return;
    if (!pendingPulse) {
      const seconds = Math.min(30, activeSeconds);
      if (seconds < 1) return;
      activeSeconds -= seconds;
      pendingPulse = { id: crypto.randomUUID(), seconds };
      sessionStorage.setItem(storageKey, JSON.stringify(pendingPulse));
    }
    const body = new FormData();
    body.set("client_event_id", pendingPulse.id);
    body.set("active_seconds", String(pendingPulse.seconds));
    sending = true;
    fetch(`/internal/brief-review-sessions/${root.dataset.reviewSession}/activity-pulses`, {
      method: "POST", body, credentials: "same-origin", keepalive: true,
    }).then((response) => {
      if (!response.ok) throw new Error(`activity pulse failed: ${response.status}`);
      pendingPulse = null;
      sessionStorage.removeItem(storageKey);
    }).catch(() => {}).finally(() => { sending = false; });
  };
  setInterval(sample, 1000);
  setInterval(flush, 15000);
  ["blur", "pagehide"].forEach((name) => addEventListener(name, flush));
  document.addEventListener("visibilitychange", () => { if (document.hidden) flush(); });
  document.addEventListener("submit", flush);
  if (pendingPulse) flush();
})();
