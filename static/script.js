const $ = (id) => document.getElementById(id);
let chosenFile = null;
let afterUrl = null;

// Real pixels = CSS pixels * devicePixelRatio. It is only a guess (see page hint).
const dpr = window.devicePixelRatio || 1;
const detectedW = Math.round(screen.width * dpr);
const detectedH = Math.round(screen.height * dpr);
$("detected").textContent = `${detectedW} x ${detectedH}`;
$("width").value = detectedW;
$("height").value = detectedH;

function showError(msg) {
  $("error").textContent = msg;
  $("error").hidden = !msg;
}

function setFile(file) {
  showError("");
  if (!file) return;
  // Cheap client-side checks; the server repeats them because clients can lie.
  if (!/\.(jpe?g|png|webp|bmp)$/i.test(file.name)) {
    return showError("Only jpg, jpeg, png, webp and bmp files are allowed.");
  }
  if (file.size > 20 * 1024 * 1024) return showError("File is larger than 20 MB.");
  chosenFile = file;
  const mb = (file.size / (1024 * 1024)).toFixed(1);
  $("dropText").textContent = `✓ ${file.name} (${mb} MB) uploaded. Click to change.`;
  drop.classList.add("has-file");
  $("go").disabled = false;

  // Read only the pixel size to show it; the image itself is never displayed.
  const url = URL.createObjectURL(file);
  const probe = new Image();
  probe.onload = () => {
    if (chosenFile === file) {
      $("dropText").textContent =
        `✓ ${file.name} (${probe.naturalWidth} x ${probe.naturalHeight}, ${mb} MB) uploaded. Click to change.`;
    }
    URL.revokeObjectURL(url); // free the memory right away
  };
  probe.onerror = () => URL.revokeObjectURL(url);
  probe.src = url;
}

const drop = $("drop");
drop.addEventListener("click", () => $("file").click());
drop.addEventListener("keydown", (e) => { if (e.key === "Enter") $("file").click(); });
$("file").addEventListener("change", (e) => setFile(e.target.files[0]));
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => {
  e.preventDefault();
  drop.classList.remove("over");
  setFile(e.dataTransfer.files[0]);
});

$("go").addEventListener("click", async () => {
  const w = parseInt($("width").value, 10);
  const h = parseInt($("height").value, 10);
  if (!(w >= 320 && w <= 7680 && h >= 320 && h <= 7680)) {
    return showError("Width and height must be between 320 and 7680.");
  }
  showError("");
  $("warnings").hidden = true;
  $("result").hidden = true;
  $("status").hidden = false;
  $("go").disabled = true;

  const form = new FormData();
  form.append("image", chosenFile);
  form.append("width", w);
  form.append("height", h);
  form.append("mode", $("mode").value);
  form.append("enhance", $("enhance").checked ? "1" : "0");
  form.append("ai_model", $("aiModel").value);
  $("status").textContent = $("enhance").checked
    ? "Processing... AI upscaling can take up to a minute."
    : "Processing...";

  try {
    const resp = await fetch("/process", { method: "POST", body: form });
    if (!resp.ok) {
      let msg = "Something went wrong.";
      try { msg = (await resp.json()).error || msg; } catch (_) {}
      return showError(msg);
    }
    const info = JSON.parse(resp.headers.get("X-Wallpaper-Info") || "{}");
    const blob = await resp.blob();
    if (afterUrl) URL.revokeObjectURL(afterUrl);
    afterUrl = URL.createObjectURL(blob);

    $("after").src = afterUrl;
    $("afterSize").textContent = `${w} x ${h}`;
    $("download").href = afterUrl;
    $("download").download = `wallpaper_${w}x${h}.png`;
    $("result").hidden = false;
    $("method").textContent = info.method ? `Enlarged with: ${info.method}` : "";
    $("deskImg").src = afterUrl;

    const list = $("warnings");
    list.innerHTML = "";
    (info.warnings || []).forEach((t) => {
      const li = document.createElement("li");
      li.textContent = t; // textContent, never innerHTML, to avoid injection
      list.appendChild(li);
    });
    list.hidden = !(info.warnings || []).length;
  } catch (err) {
    showError("Could not reach the server. Is it running?");
  } finally {
    $("status").hidden = true;
    $("go").disabled = false;
  }
});

// ---- Desktop preview ----
const desk = $("desk");
const FAKE_ICONS = ["This PC", "Recycle Bin", "Chrome", "VS Code", "Discord",
  "Files", "Notes", "Music", "Games", "Photos", "Settings", "Docs"];
FAKE_ICONS.forEach((name) => {
  const el = document.createElement("div");
  el.className = "desk-icon";
  el.innerHTML = "<i></i>";
  el.appendChild(document.createTextNode(name));
  $("deskIcons").appendChild(el);
});

$("previewDesktop").addEventListener("click", async () => {
  desk.hidden = false;
  desk.classList.remove("zoomed");
  $("deskZoom").textContent = "Zoom in";
  $("deskClock").textContent = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  // Full screen hides the browser bars so the preview matches the real desktop.
  try { await desk.requestFullscreen(); } catch (_) {}
});

function closeDesk() {
  desk.hidden = true;
  if (document.fullscreenElement) document.exitFullscreen();
}
$("deskClose").addEventListener("click", closeDesk);
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !desk.hidden) closeDesk(); });
// Leaving full screen with Esc is handled by the browser; close the overlay too.
document.addEventListener("fullscreenchange", () => { if (!document.fullscreenElement) desk.hidden = true; });

$("deskToggleUi").addEventListener("click", () => {
  const hidden = desk.classList.toggle("no-ui");
  $("deskToggleUi").textContent = hidden ? "Show icons" : "Hide icons";
});

// Zoom in: show the image larger than the screen to inspect sharpness up close.
$("deskZoom").addEventListener("click", () => {
  const zoomed = desk.classList.toggle("zoomed");
  $("deskZoom").textContent = zoomed ? "Fit to screen" : "Zoom in";
});
