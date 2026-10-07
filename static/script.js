const $ = (id) => document.getElementById(id);

// Mirrors core/analyzer.py and core/upscaler.py so the page can explain the
// result before the server runs. The server stays the source of truth.
let LIMITS = { min_side: 320, max_side: 7680, max_megapixels: 50, max_upload_mb: 20 };
const AI_SCALES = { anime: [2, 3, 4], photo: [4] };
const AI_MAX_OUTPUT_MP = 50;

const state = {
  file: null,
  img: null,          // decoded source, used for the live preview
  srcW: 0, srcH: 0,
  aiAvailable: null,  // null = unknown (status request failed)
  result: null,       // { url, key, w, h, aiUsed }
  busy: false,
  view: "preview",
};

// ---------- Settings ----------
// Real pixels = CSS pixels * devicePixelRatio. It is only a guess (see page hint).
const dpr = window.devicePixelRatio || 1;
const detectedW = Math.round(screen.width * dpr);
const detectedH = Math.round(screen.height * dpr);
$("detected").textContent = `${detectedW} × ${detectedH}`;
$("width").value = detectedW;
$("height").value = detectedH;

const settings = () => ({
  w: parseInt($("width").value, 10),
  h: parseInt($("height").value, 10),
  mode: document.querySelector('input[name="mode"]:checked').value,
  enhance: $("enhance").checked,
  model: document.querySelector('input[name="aiModel"]:checked').value,
});
const settingsKey = (s) => JSON.stringify(s);

function setFrameRatio(w, h) {
  $("screen").style.setProperty("--ratio", `${w} / ${h}`);
  $("screen").style.setProperty("--ratio-num", String(w / h));
}

function sizeError({ w, h }) {
  const { min_side: lo, max_side: hi, max_megapixels: mp } = LIMITS;
  if (!(w >= lo && w <= hi && h >= lo && h <= hi)) return `Width and height must be between ${lo} and ${hi} px.`;
  if (w * h > mp * 1e6) return `Screen size is above ${mp} megapixels.`;
  return "";
}

fetch("/status")
  .then((r) => r.json())
  .then((d) => {
    state.aiAvailable = d.ai_available;
    LIMITS = d.limits || LIMITS;
    $("dropLimits").textContent =
      `JPG, PNG, WebP, BMP · up to ${LIMITS.max_upload_mb} MB · ${LIMITS.max_megapixels} megapixels`;
    refresh();
  })
  .catch(() => {});

// ---------- Theme ----------
$("themeBtn").addEventListener("click", () => {
  const root = document.documentElement;
  const dark = root.dataset.theme
    ? root.dataset.theme === "dark"
    : matchMedia("(prefers-color-scheme: dark)").matches;
  root.dataset.theme = dark ? "light" : "dark";
  try { localStorage.setItem("theme", root.dataset.theme); } catch (_) {}
});

// ---------- File input ----------
function showError(msg) {
  $("error").textContent = msg;
  $("error").hidden = !msg;
}

let toastTimer;
function toast(msg) {
  $("toast").textContent = msg;
  $("toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { $("toast").hidden = true; }, 2400);
}

function setFile(file) {
  if (!file || state.busy) return;
  showError("");
  // Cheap client-side checks; the server repeats them because clients can lie.
  if (!/\.(jpe?g|png|webp|bmp)$/i.test(file.name)) {
    return showError("Only JPG, PNG, WebP and BMP files are supported.");
  }
  if (file.size > LIMITS.max_upload_mb * 1024 * 1024) {
    return showError(`That file is larger than ${LIMITS.max_upload_mb} MB.`);
  }

  clearResult();
  if (state.img) URL.revokeObjectURL(state.img.src);
  state.file = file;
  state.img = null;
  state.srcW = state.srcH = 0;

  const mb = file.size < 1024 * 1024
    ? `${Math.max(1, Math.round(file.size / 1024))} KB`
    : `${(file.size / (1024 * 1024)).toFixed(1)} MB`;
  $("fileName").textContent = file.name;
  $("fileInfo").textContent = `${mb} · reading…`;
  $("drop").hidden = true;
  $("workspace").hidden = false;
  document.documentElement.classList.add("has-file");

  const url = URL.createObjectURL(file);
  const img = new Image();
  img.onload = () => {
    if (state.file !== file) return URL.revokeObjectURL(url);
    state.img = img;
    state.srcW = img.naturalWidth;
    state.srcH = img.naturalHeight;
    $("thumb").src = url;
    $("fileInfo").textContent = `${state.srcW} × ${state.srcH} · ${mb}`;
    refresh();
  };
  img.onerror = () => {
    URL.revokeObjectURL(url);
    if (state.file !== file) return;
    // The browser could not decode it; the server may still manage, so allow trying.
    $("thumb").removeAttribute("src");
    $("fileInfo").textContent = `${mb} · no preview available`;
    refresh();
  };
  img.src = url;
  refresh();
}

function clearFile() {
  if (state.busy) return;
  if (state.img) URL.revokeObjectURL(state.img.src);
  clearResult();
  Object.assign(state, { file: null, img: null, srcW: 0, srcH: 0 });
  $("file").value = "";
  $("workspace").hidden = true;
  $("drop").hidden = false;
  document.documentElement.classList.remove("has-file");
  showError("");
  refresh();
  $("pick").focus();
}

const drop = $("drop");
$("pick").addEventListener("click", () => $("file").click());
$("file").addEventListener("change", (e) => setFile(e.target.files[0]));
$("replace").addEventListener("click", () => $("file").click());
$("clear").addEventListener("click", clearFile);

// Drag and drop works on both the empty drop zone and the loaded workspace.
for (const zone of [drop, $("workspace")]) {
  zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("over"); });
  zone.addEventListener("dragleave", (e) => {
    if (!zone.contains(e.relatedTarget)) zone.classList.remove("over");
  });
  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    zone.classList.remove("over");
    setFile(e.dataTransfer.files[0]);
  });
}

// Paste an image copied from a browser, screenshot tool, etc.
document.addEventListener("paste", (e) => {
  if (e.target.matches("input")) return;
  const item = [...(e.clipboardData?.items || [])].find((i) => i.type.startsWith("image/"));
  if (!item) return;
  const blob = item.getAsFile();
  const ext = { "image/jpeg": "jpg", "image/webp": "webp", "image/bmp": "bmp" }[blob.type] || "png";
  setFile(new File([blob], `pasted-image.${ext}`, { type: blob.type }));
});

// ---------- Settings events ----------
for (const id of ["width", "height"]) $(id).addEventListener("input", refresh);
document.querySelectorAll('input[name="mode"], input[name="aiModel"], #enhance')
  .forEach((el) => el.addEventListener("change", refresh));

$("swap").addEventListener("click", () => {
  [$("width").value, $("height").value] = [$("height").value, $("width").value];
  refresh();
});
$("resetSize").addEventListener("click", () => {
  $("width").value = detectedW;
  $("height").value = detectedH;
  refresh();
});
document.querySelectorAll(".presets button").forEach((b) => b.addEventListener("click", () => {
  $("width").value = b.dataset.w;
  $("height").value = b.dataset.h;
  refresh();
}));

// ---------- Analysis (mirrors the server) ----------
function enlargementNeeded(sw, sh, tw, th, mode) {
  return mode.startsWith("fit_") ? Math.min(tw / sw, th / sh) : Math.max(tw / sw, th / sh);
}

function analysis(s) {
  if (!state.srcW || sizeError(s)) return null;
  const { srcW: sw, srcH: sh } = state;
  const scale = enlargementNeeded(sw, sh, s.w, s.h, s.mode);
  const srcRatio = sw / sh;
  const tRatio = s.w / s.h;
  // Share of the image area removed by a center crop (fill mode).
  const cropped = 1 - Math.min(srcRatio, tRatio) / Math.max(srcRatio, tRatio);
  const aiScale = AI_SCALES[s.model].find((f) => f >= scale) || 4;
  return {
    scale, cropped, aiScale,
    ratioDiff: Math.abs(srcRatio - tRatio) / tRatio,
    aiOutputMp: (sw * aiScale * sh * aiScale) / 1e6,
  };
}

const fmtScale = (x) => (x >= 10 ? x.toFixed(0) : x.toFixed(x < 1.05 && x > 0.95 ? 2 : 1));

function renderFacts(s, a) {
  const facts = $("facts");
  facts.innerHTML = "";
  const add = (label, value, tone = "") => {
    const el = document.createElement("span");
    el.className = `fact ${tone}`;
    el.append(label + " ");
    const b = document.createElement("b");
    b.textContent = value;
    el.append(b);
    facts.append(el);
  };
  if (!state.srcW) return;
  add("Source", `${state.srcW} × ${state.srcH}`);
  if (sizeError(s)) return;
  add("Output", `${s.w} × ${s.h}`);
  if (!a) return;
  if (a.scale > 1.01) add("Enlarged", `${fmtScale(a.scale)}×`, a.scale > 1.5 && !willUseAi(s, a) ? "warn" : "");
  else add("Scaled", a.scale < 0.99 ? `down ${fmtScale(1 / a.scale)}×` : "1:1", "good");
  if (s.mode === "fill" && a.cropped > 0.005) add("Cropped", `${Math.round(a.cropped * 100)}%`, a.ratioDiff > 0.25 ? "warn" : "");
  if (s.mode === "stretch" && a.ratioDiff > 0.02) add("Distortion", `${Math.round(a.ratioDiff * 100)}%`, "warn");
}

const willUseAi = (s, a) => s.enhance && state.aiAvailable !== false && a && a.scale > 1;

function renderAiNote(s, a) {
  const note = $("aiNote");
  $("aiOptions").classList.toggle("off", !s.enhance);
  let text = "", tone = "";
  if (!s.enhance) {
    text = "Off. Small images are enlarged with standard Lanczos resizing.";
  } else if (state.aiAvailable === false) {
    text = "AI upscaling isn't available on this server, so standard (Lanczos) resizing will be used.";
    tone = "warn";
  } else if (!a) {
    text = "Used only when your image is smaller than the screen.";
  } else if (a.scale <= 1) {
    text = "Not needed: your image is already big enough and will be scaled down cleanly.";
    tone = "good";
  } else if (a.aiOutputMp > AI_MAX_OUTPUT_MP) {
    text = `The AI result would be ${a.aiOutputMp.toFixed(0)} MP, above the ${AI_MAX_OUTPUT_MP} MP memory limit, so standard resizing will be used.`;
    tone = "warn";
  } else {
    text = `Will upscale ${a.aiScale}× with AI, then fit to the exact size. This can take up to a minute.`;
    tone = "good";
  }
  note.textContent = text;
  note.className = `note ${tone}`;
  note.hidden = false;
}

const MODE_NAMES = { fit_blur: "Blurred background", fit_black: "Black bars", fill: "Fill", stretch: "Stretch" };

function renderSummary(s, sizeBad) {
  const el = $("summary");
  el.textContent = "";
  const parts = [sizeBad ? "Invalid size" : `${s.w} × ${s.h}`, MODE_NAMES[s.mode], s.enhance ? "AI on" : "AI off"];
  parts.forEach((p, i) => {
    if (i) el.append(" · ");
    const b = document.createElement("b");
    b.textContent = p;
    el.append(b);
  });
}

// ---------- Live preview ----------
const hasCtxFilter = "filter" in CanvasRenderingContext2D.prototype;

function coverRect(sw, sh, tw, th) {
  // Same center crop as core/cropper.py.
  if (sw * th > tw * sh) {
    const w = (sh * tw) / th;
    return [(sw - w) / 2, 0, w, sh];
  }
  const h = (sw * th) / tw;
  return [0, (sh - h) / 2, sw, h];
}

function containRect(sw, sh, cw, ch) {
  const k = Math.min(cw / sw, ch / sh);
  const w = sw * k, h = sh * k;
  return [(cw - w) / 2, (ch - h) / 2, w, h];
}

/** Draw the wallpaper for target tw×th onto a canvas of size cw×ch. */
function drawWallpaper(canvas, img, tw, th, mode) {
  const ctx = canvas.getContext("2d");
  const { width: cw, height: ch } = canvas;
  const sw = img.naturalWidth, sh = img.naturalHeight;
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high";
  ctx.clearRect(0, 0, cw, ch);

  if (mode === "stretch") return ctx.drawImage(img, 0, 0, cw, ch);
  if (mode === "fill") return ctx.drawImage(img, ...coverRect(sw, sh, tw, th), 0, 0, cw, ch);

  if (mode === "fit_blur") {
    // Same recipe as core/fitter.py: tiny cover crop, blur, enlarge, darken 30%.
    const small = document.createElement("canvas");
    small.width = hasCtxFilter ? 192 : 24;  // without ctx.filter, a tinier image fakes the blur
    small.height = Math.max(1, Math.round((small.width * th) / tw));
    const sctx = small.getContext("2d");
    if (hasCtxFilter) sctx.filter = `blur(${(6 * small.width) / 192}px)`;
    sctx.drawImage(img, ...coverRect(sw, sh, tw, th), -8, -8, small.width + 16, small.height + 16);
    ctx.drawImage(small, 0, 0, cw, ch);
    ctx.fillStyle = "rgba(0,0,0,.3)";
    ctx.fillRect(0, 0, cw, ch);
  } else {
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, cw, ch);
  }
  ctx.drawImage(img, ...containRect(sw, sh, cw, ch));
}

function sizeCanvasToBox(canvas, s) {
  // Render at display resolution (capped at the target size) to stay fast.
  const box = $("screen").getBoundingClientRect();
  const k = Math.min(1, (box.width * dpr) / s.w);
  canvas.width = Math.max(1, Math.round(s.w * k));
  canvas.height = Math.max(1, Math.round(s.h * k));
}

function renderPreview(s) {
  const ok = !sizeError(s);
  if (ok) setFrameRatio(s.w, s.h);
  const canvas = $("previewCanvas");
  if (!state.img || !ok) {
    canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
    return;
  }
  sizeCanvasToBox(canvas, s);
  drawWallpaper(canvas, state.img, s.w, s.h, s.mode);
}

// ---------- View tabs ----------
const VIEWS = { preview: "tabPreview", result: "tabResult", compare: "tabCompare" };

function setView(view) {
  state.view = view;
  for (const [v, tab] of Object.entries(VIEWS)) $(tab).setAttribute("aria-selected", String(v === view));
  $("previewCanvas").hidden = view !== "preview";
  $("resultImg").hidden = view !== "result";
  $("compare").hidden = view !== "compare";
  const s = settings();
  const r = state.result;
  // The frame follows whatever is being shown, so an outdated result keeps its own shape.
  if (r && view !== "preview") setFrameRatio(r.w, r.h);
  else if (!sizeError(s)) setFrameRatio(s.w, s.h);
  $("viewCaption").textContent = {
    preview: "Approximate, rendered in your browser",
    result: r ? `Final output · ${r.w} × ${r.h} PNG` : "",
    compare: "Drag to compare a plain resize with the AI output",
  }[view];
  if (view === "compare") renderCompare();
  if (view === "preview") renderPreview(s);
}
for (const [v, tab] of Object.entries(VIEWS)) $(tab).addEventListener("click", () => setView(v));

$("tabPreview").parentElement.addEventListener("keydown", (e) => {
  if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
  const tabs = Object.values(VIEWS).map($).filter((t) => !t.disabled);
  const i = tabs.indexOf(document.activeElement);
  const next = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
  next.focus();
  next.click();
});

function renderCompare() {
  const r = state.result;
  if (!r || !state.img) return;
  const canvas = $("beforeCanvas");
  sizeCanvasToBox(canvas, r);
  drawWallpaper(canvas, state.img, r.w, r.h, r.mode);
}

function setCompare(p) {
  $("compareRange").value = p;
  const clip = `inset(0 0 0 ${p}%)`;
  $("afterClip").style.clipPath = clip;
  $("afterClip").style.webkitClipPath = clip;
  $("divider").style.left = `${p}%`;
}
$("compareRange").addEventListener("input", (e) => setCompare(e.target.value));

// Drag anywhere on the image (mouse, pen or finger). touch-action: pan-y in
// the CSS keeps vertical page scrolling working on phones.
const compareEl = $("compare");
function compareAt(e) {
  const r = compareEl.getBoundingClientRect();
  setCompare(Math.max(0, Math.min(100, ((e.clientX - r.left) / r.width) * 100)).toFixed(1));
}
compareEl.addEventListener("pointerdown", (e) => {
  compareEl.setPointerCapture(e.pointerId);
  compareAt(e);
  $("compareRange").focus({ preventScroll: true });
});
compareEl.addEventListener("pointermove", (e) => {
  if (compareEl.hasPointerCapture(e.pointerId)) compareAt(e);
});

// ---------- Central refresh ----------
function refresh() {
  const s = settings();
  const err = sizeError(s);
  const a = analysis(s);
  const sizeBad = Number.isNaN(s.w) || Number.isNaN(s.h) ? "Enter a width and a height." : err;

  $("sizeError").textContent = sizeBad;
  $("sizeError").hidden = !sizeBad;
  $("width").setAttribute("aria-invalid", String(!!sizeBad));
  $("height").setAttribute("aria-invalid", String(!!sizeBad));
  $("resetSize").hidden = s.w === detectedW && s.h === detectedH;
  document.querySelectorAll(".presets button").forEach((b) => {
    b.classList.toggle("active", +b.dataset.w === s.w && +b.dataset.h === s.h);
  });

  renderAiNote(s, a);
  renderFacts(s, a);
  renderSummary(s, sizeBad);
  if (state.view === "preview") renderPreview(s);

  const stale = !!state.result && state.result.key !== settingsKey(s);
  $("stale").hidden = !stale || state.busy;
  $("goLabel").textContent = state.result ? (stale ? "Update wallpaper" : "Make again") : "Make wallpaper";
  $("go").disabled = !state.file || !!sizeBad || state.busy;
}

// Keep the canvases sharp when the layout changes size.
let resizeRaf;
new ResizeObserver(() => {
  cancelAnimationFrame(resizeRaf);
  resizeRaf = requestAnimationFrame(() => {
    if (state.view === "preview") renderPreview(settings());
    else if (state.view === "compare") renderCompare();
  });
}).observe($("screen"));

// ---------- Processing ----------
function clearResult() {
  if (state.result) URL.revokeObjectURL(state.result.url);
  state.result = null;
  $("resultActions").hidden = true;
  $("warnings").hidden = true;
  $("stale").hidden = true;
  $("tabResult").disabled = true;
  $("tabCompare").disabled = true;
  setView("preview");
}

function setBusy(on, aiExpected) {
  state.busy = on;
  $("busy").hidden = !on;
  $("replace").disabled = $("clear").disabled = on;
  clearInterval(setBusy.timer);
  if (on) {
    const start = Date.now();
    $("busyText").textContent = aiExpected ? "Upscaling with AI…" : "Making your wallpaper…";
    $("busyTime").textContent = aiExpected ? "This can take up to a minute" : "";
    setBusy.timer = setInterval(() => {
      const sec = Math.floor((Date.now() - start) / 1000);
      if (sec >= 2) $("busyTime").textContent = `${sec}s elapsed${aiExpected ? " · up to a minute" : ""}`;
    }, 1000);
  }
  refresh();
}

async function generate() {
  const s = settings();
  if (!state.file || sizeError(s) || state.busy) return;
  showError("");
  // Show the preview under the spinner, so the user sees what is being made.
  setView("preview");
  setBusy(true, willUseAi(s, analysis(s)));

  const form = new FormData();
  form.append("image", state.file);
  form.append("width", s.w);
  form.append("height", s.h);
  form.append("mode", s.mode);
  form.append("enhance", s.enhance ? "1" : "0");
  form.append("ai_model", s.model);

  try {
    const resp = await fetch("/process", { method: "POST", body: form });
    if (!resp.ok) {
      let msg = "Something went wrong while processing the image.";
      try { msg = (await resp.json()).error || msg; } catch (_) {}
      return showError(msg);
    }
    let info = {};
    try { info = JSON.parse(resp.headers.get("X-Wallpaper-Info") || "{}"); } catch (_) {}
    const blob = await resp.blob();
    showResult(s, blob, info);
  } catch (_) {
    showError("Could not reach the server. Check your connection and try again.");
  } finally {
    setBusy(false);
  }
}

function showResult(s, blob, info) {
  if (state.result) URL.revokeObjectURL(state.result.url);
  const url = URL.createObjectURL(blob);
  const aiUsed = /Real-ESRGAN/.test(info.method || "");
  state.result = { url, blob, key: settingsKey(s), w: s.w, h: s.h, mode: s.mode, aiUsed };

  const base = state.file.name.replace(/\.[^.]+$/, "").slice(0, 60) || "wallpaper";
  $("resultImg").src = url;
  $("compareAfter").src = url;
  $("deskImg").src = url;
  $("download").href = url;
  $("download").download = `${base}_${s.w}x${s.h}.png`;
  $("method").textContent = info.method ? `Enlarged with ${info.method}` : "";
  $("resultActions").hidden = false;
  $("tabResult").disabled = false;
  // Compare is only meaningful when AI changed the pixels; otherwise both sides match.
  $("tabCompare").disabled = !aiUsed;
  $("tabCompare").title = aiUsed ? "" : "Available when AI enhance was used";

  const list = $("warnings");
  list.innerHTML = "";
  for (const t of info.warnings || []) {
    const li = document.createElement("li");
    li.textContent = t; // textContent, never innerHTML, to avoid injection
    list.append(li);
  }
  list.hidden = !(info.warnings || []).length;

  setView("result");
  toast("Wallpaper ready");
}

$("go").addEventListener("click", generate);
$("staleGo").addEventListener("click", generate);
document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); generate(); }
});

// Copy to clipboard (Chromium and recent Safari/Firefox support image/png).
if (navigator.clipboard && window.ClipboardItem) {
  $("copyBtn").hidden = false;
  $("copyBtn").addEventListener("click", async () => {
    try {
      await navigator.clipboard.write([new ClipboardItem({ "image/png": state.result.blob })]);
      toast("Copied to clipboard");
    } catch (_) {
      toast("Your browser blocked copying. Use Download instead.");
    }
  });
}

// ---------- Desktop preview ----------
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

let deskOpener = null;
$("previewDesktop").addEventListener("click", async () => {
  deskOpener = document.activeElement;
  desk.hidden = false;
  desk.classList.remove("zoomed");
  $("deskImg").style.width = "";
  $("deskZoom").textContent = "Zoom to 100%";
  $("deskClock").textContent = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  $("deskClose").focus();
  // Full screen hides the browser bars so the preview matches the real desktop.
  // iPhone Safari has no element full screen; the overlay still covers the page.
  const enter = desk.requestFullscreen || desk.webkitRequestFullscreen;
  try { if (enter) await enter.call(desk); } catch (_) {}
});

const fullscreenEl = () => document.fullscreenElement || document.webkitFullscreenElement;

function closeDesk() {
  if (desk.hidden) return;
  desk.hidden = true;
  if (fullscreenEl()) (document.exitFullscreen || document.webkitExitFullscreen).call(document);
  deskOpener?.focus();
}
$("deskClose").addEventListener("click", closeDesk);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDesk(); });
// Leaving full screen with Esc is handled by the browser; close the overlay too.
for (const ev of ["fullscreenchange", "webkitfullscreenchange"]) {
  document.addEventListener(ev, () => { if (!fullscreenEl()) closeDesk(); });
}

$("deskToggleUi").addEventListener("click", () => {
  const hidden = desk.classList.toggle("no-ui");
  $("deskToggleUi").textContent = hidden ? "Show icons" : "Hide icons";
});

// Zoom to 100%: one image pixel per screen pixel, to inspect sharpness up close.
$("deskZoom").addEventListener("click", () => {
  const zoomed = desk.classList.toggle("zoomed");
  // Divide by devicePixelRatio so Windows display scaling doesn't enlarge it.
  $("deskImg").style.width = zoomed ? `${$("deskImg").naturalWidth / dpr}px` : "";
  $("deskZoom").textContent = zoomed ? "Fit to screen" : "Zoom to 100%";
});

// ---------- Sidebar: resize and collapse ----------
const root = document.documentElement;
const SIDE_MIN = 300;
const SIDE_DEFAULT = 360;
const sideMax = () => Math.min(560, Math.round(window.innerWidth * 0.5));
const store = (k, v) => { try { localStorage.setItem(k, v); } catch (_) {} };

function setSideWidth(px, save = true) {
  const w = Math.round(Math.max(SIDE_MIN, Math.min(sideMax(), px)));
  root.style.setProperty("--side-w", `${w}px`);
  const handle = $("resizer");
  handle.setAttribute("aria-valuenow", String(w));
  handle.setAttribute("aria-valuemin", String(SIDE_MIN));
  handle.setAttribute("aria-valuemax", String(sideMax()));
  if (save) store("sidebarWidth", w);
}
setSideWidth($("sidebar").getBoundingClientRect().width || SIDE_DEFAULT, false);

const resizer = $("resizer");
resizer.addEventListener("pointerdown", (e) => {
  e.preventDefault();
  resizer.setPointerCapture(e.pointerId);
  root.classList.add("resizing");
});
resizer.addEventListener("pointermove", (e) => {
  if (!resizer.hasPointerCapture(e.pointerId)) return;
  setSideWidth(e.clientX - $("sidebar").getBoundingClientRect().left);
});
const stopResize = () => root.classList.remove("resizing");
resizer.addEventListener("pointerup", stopResize);
resizer.addEventListener("pointercancel", stopResize);
resizer.addEventListener("dblclick", () => setSideWidth(SIDE_DEFAULT));
resizer.addEventListener("keydown", (e) => {
  const cur = $("sidebar").getBoundingClientRect().width;
  const step = e.shiftKey ? 48 : 16;
  const keys = { ArrowLeft: cur - step, ArrowRight: cur + step, Home: SIDE_MIN, End: sideMax() };
  if (e.key in keys) { e.preventDefault(); setSideWidth(keys[e.key]); }
});

function setCollapsed(on) {
  root.classList.toggle("side-collapsed", on);
  store("sidebarCollapsed", on ? "1" : "0");
  (on ? $("expandBtn") : $("collapseBtn")).focus();
}
$("collapseBtn").addEventListener("click", () => setCollapsed(true));
$("expandBtn").addEventListener("click", () => setCollapsed(false));

// On phones the action bar is fixed to the bottom; reserve exactly its height.
new ResizeObserver(([entry]) => {
  root.style.setProperty("--foot-h", `${Math.ceil(entry.target.getBoundingClientRect().height)}px`);
}).observe(document.querySelector(".side-foot"));

refresh();
