// Runs in <head> before first paint: apply the saved theme and sidebar width
// so the page doesn't flash or jump when it loads.
try {
  const t = localStorage.getItem("theme");
  if (t) document.documentElement.dataset.theme = t;
  const w = parseInt(localStorage.getItem("sidebarWidth"), 10);
  if (w) document.documentElement.style.setProperty("--side-w", w + "px");
  if (localStorage.getItem("sidebarCollapsed") === "1") document.documentElement.classList.add("side-collapsed");
} catch (_) {}
