// Zeroing: shoot a few targets so the cursor lands where the gun's
// sights point rather than where the camera does.
//
// The server runs the whole flow (zeroing.py): which targets, the fit,
// storing it for this phone. This page only sends start / finish /
// cancel / reset and shows what every stats message says. The trigger
// is untouched -- while zeroing, the server takes a press as a shot and
// clicks nothing in the game.
//
// Loaded after capture.js, whose `state` and `send` it uses.

"use strict";

(function zeroingPanel() {
  const el = {};
  for (const id of [
    "zeroing-start", "zeroing-finish", "zeroing-cancel", "zeroing-reset",
    "zeroing-state", "zeroing-prompt",
  ]) {
    el[id] = document.getElementById(id);
  }

  let active = false;

  function connected() {
    return state.socket !== null && state.socket.readyState === WebSocket.OPEN;
  }

  function refreshButtons() {
    const on = connected();
    el["zeroing-start"].disabled = !on || active;
    el["zeroing-finish"].disabled = !on || !active;
    el["zeroing-cancel"].disabled = !on || !active;
    el["zeroing-reset"].disabled = !on || active;
  }

  // Only written when it changes: this runs for every frame's stats.
  function put(id, text) {
    if (el[id].textContent !== text) el[id].textContent = text;
  }

  function render(zeroing) {
    if (!zeroing) return;
    active = zeroing.active;
    const target = zeroing.target;
    if (active && target) {
      put("zeroing-state", `target ${target.index + 1} of ${target.count}`);
      let prompt =
        `Aim through the sights at the ${target.label} and pull the trigger.`;
      if (target.optional) {
        prompt += " Optional: step about a metre closer or farther first, or tap Done.";
      }
      if (zeroing.message) prompt += `\n${zeroing.message}`;
      put("zeroing-prompt", prompt);
    } else {
      put(
        "zeroing-state",
        zeroing.zeroed
          ? "zeroed" +
              (zeroing.residual === null
                ? ""
                : ` (±${(zeroing.residual * 100).toFixed(2)}% of width)`)
          : "not zeroed",
      );
      put("zeroing-prompt", zeroing.message || "");
    }
    refreshButtons();
  }

  function act(action) {
    send(JSON.stringify({ type: "zeroing", action }));
  }

  el["zeroing-start"].addEventListener("click", () => act("start"));
  el["zeroing-finish"].addEventListener("click", () => act("finish"));
  el["zeroing-cancel"].addEventListener("click", () => act("cancel"));
  el["zeroing-reset"].addEventListener("click", () => {
    if (window.confirm("Forget this phone's zero and aim with the camera centre?")) {
      act("reset");
    }
  });

  document.addEventListener("boresight:stats", (event) => render(event.detail.zeroing));
  // The socket opens and closes without telling this script; a stopped
  // stream must not leave live buttons behind.
  setInterval(() => {
    if (!connected()) active = false;
    refreshButtons();
  }, 500);
  refreshButtons();
})();
