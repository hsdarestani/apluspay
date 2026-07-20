document.addEventListener("DOMContentLoaded", () => {
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
  document.querySelectorAll(".flash").forEach((flash) => setTimeout(() => flash.classList.add("flash-hide"), 4200));
  document.querySelectorAll(".qr-grid").forEach((grid) => {
    const token = grid.parentElement.dataset.qr || "A+PAY";
    let seed = 0;
    for (const char of token) seed = (seed * 31 + char.charCodeAt(0)) >>> 0;
    for (let i = 0; i < 121; i += 1) {
      const cell = document.createElement("span");
      seed = (seed * 1664525 + 1013904223) >>> 0;
      if (seed % 3 !== 0 || i < 15 || i > 105) cell.className = "filled";
      grid.appendChild(cell);
    }
  });
});
