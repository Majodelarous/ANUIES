import assert from "node:assert/strict";
import { test } from "node:test";

import { ActiveCall } from "baileys-caller";

test("colgar desde el puente avisa que la llamada terminó", async () => {
  const motor = { endCall: () => {} };
  const llamada = new ActiveCall("X", motor, 0);
  let motivo = null;
  llamada.on("ended", (m) => { motivo = m; });
  llamada.end();
  assert.equal(motivo, "hangup");
  assert.equal(await llamada.waitForEnd(), "hangup");
});
