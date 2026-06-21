const mode = document.querySelector("#mode");
const trackingMode = document.querySelector("#trackingMode");
const cameraIndex = document.querySelector("#cameraIndex");
const gridCols = document.querySelector("#gridCols");
const gridRows = document.querySelector("#gridRows");
const apply = document.querySelector("#apply");
const toggle = document.querySelector("#toggle");
const reset = document.querySelector("#reset");
const shutdown = document.querySelector("#shutdown");
const runState = document.querySelector("#runState");
const trackingState = document.querySelector("#trackingState");
const fps = document.querySelector("#fps");
const attempts = document.querySelector("#attempts");
const crcFails = document.querySelector("#crcFails");
const magicFails = document.querySelector("#magicFails");
const okFrames = document.querySelector("#okFrames");
const gridSize = document.querySelector("#gridSize");
const message = document.querySelector("#message");
const messageStage = document.querySelector(".message-card");
const receivedImage = document.querySelector("#receivedImage");
const receivedFile = document.querySelector("#receivedFile");
const decoderStatus = document.querySelector("#decoderStatus");
const logs = document.querySelector("#logs");
const frameEvents = document.querySelector("#frameEvents");
const frameCounters = document.querySelector("#frameCounters");

let running = true;
let controlsDirty = false;

[mode, trackingMode, cameraIndex, gridCols, gridRows].forEach((control) => {
  control.addEventListener("input", () => {
    controlsDirty = true;
  });
  control.addEventListener("change", () => {
    controlsDirty = true;
  });
});

async function postJson(url, payload = {}) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return response.json();
}

function readInt(input, fallback) {
  const value = Number.parseInt(input.value, 10);
  return Number.isFinite(value) ? value : fallback;
}

apply.addEventListener("click", async () => {
  await postJson("/api/config", {
    mode: mode.value,
    tracking_mode: "center",
    camera_index: readInt(cameraIndex, 0),
    grid_cols: readInt(gridCols, 25),
    grid_rows: readInt(gridRows, 50),
    running,
  });
  controlsDirty = false;
  await refresh();
});

toggle.addEventListener("click", async () => {
  running = !running;
  await postJson("/api/config", { running });
  await refresh();
});

reset.addEventListener("click", async () => {
  await postJson("/api/reset");
  await refresh();
});

shutdown.addEventListener("click", async () => {
  shutdown.disabled = true;
  shutdown.textContent = "Apagando";
  try {
    await postJson("/api/shutdown");
  } catch {
    // The server is expected to close the connection shortly after this.
  }
});

function renderList(target, lines = []) {
  target.replaceChildren(
    ...lines.map((line) => {
      const item = document.createElement("li");
      item.textContent = line;
      return item;
    }),
  );
}

async function refresh() {
  const status = await fetch("/api/status", { cache: "no-store" }).then((r) => r.json());
  const editingControl = [mode, trackingMode, cameraIndex, gridCols, gridRows].includes(document.activeElement);
  if (!controlsDirty && !editingControl) {
    mode.value = status.mode;
    trackingMode.value = "center";
    cameraIndex.value = status.camera_index;
    gridCols.value = status.grid_cols || 25;
    gridRows.value = status.grid_rows || 50;
  }
  running = status.running;

  runState.textContent = running ? "activo" : "pausa";
  runState.style.color = running ? "var(--accent-ink)" : "var(--warn)";
  toggle.textContent = running ? "Pausar" : "Reanudar";
  trackingState.textContent = "center";

  fps.textContent = status.fps.toFixed(1);
  attempts.textContent = String(status.screen_decode_attempts || 0);
  crcFails.textContent = String(status.screen_crc_failures || 0);
  magicFails.textContent = String(status.screen_magic_failures || 0);
  okFrames.textContent = String(status.optical_frames_ok);
  gridSize.textContent = `${status.grid_cols || 25}x${status.grid_rows || 50}`;
  message.textContent = status.last_message || "";

  if (status.last_payload_type === "image" && status.last_image_url) {
    messageStage.classList.add("has-image");
    messageStage.classList.remove("has-file");
    receivedImage.src = `${status.last_image_url}?t=${status.last_message_at || Date.now()}`;
    receivedFile.removeAttribute("href");
  } else if (status.last_payload_type === "file" && status.last_file_url) {
    messageStage.classList.remove("has-image");
    messageStage.classList.add("has-file");
    receivedImage.removeAttribute("src");
    receivedFile.href = status.last_file_url;
    receivedFile.download = status.last_file_name || "received.bin";
    receivedFile.textContent = `Descargar ${status.last_file_name || "archivo"}`;
  } else {
    messageStage.classList.remove("has-image");
    messageStage.classList.remove("has-file");
    receivedImage.removeAttribute("src");
    receivedFile.removeAttribute("href");
  }

  decoderStatus.textContent = status.decoder_status || "idle";
  frameCounters.textContent = `frames ${status.screen_frames_seen} - ok ${status.optical_frames_ok} - trama ${status.frame_bytes || 0} B - payload ${status.chunk_size || 0} B`;
  renderList(logs, status.logs);
  renderList(frameEvents, status.frame_events || []);
}

setInterval(refresh, 500);
refresh();

