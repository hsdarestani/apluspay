(() => {
  const byAll = (selector) => [...document.querySelectorAll(selector)];

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => {}));
  }

  let installPrompt = null;
  const installButtons = byAll("[data-install-app]");
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    installPrompt = event;
    installButtons.forEach((button) => { button.hidden = false; });
  });
  installButtons.forEach((button) => button.addEventListener("click", async () => {
    if (!installPrompt) return;
    installPrompt.prompt();
    await installPrompt.userChoice;
    installPrompt = null;
    installButtons.forEach((item) => { item.hidden = true; });
  }));

  byAll(".flash").forEach((flash) => {
    const close = () => flash.classList.add("flash-hide");
    flash.querySelector("button")?.addEventListener("click", close);
    window.setTimeout(close, 5200);
  });

  byAll(".tab-button").forEach((button) => button.addEventListener("click", () => {
    const target = button.dataset.tabTarget;
    byAll(".tab-button").forEach((item) => item.classList.toggle("active", item === button));
    byAll(".tab-panel").forEach((panel) => panel.classList.toggle("active", panel.dataset.tab === target));
    history.replaceState(null, "", `#${target}`);
  }));
  const initialTab = location.hash.replace("#", "");
  if (initialTab) document.querySelector(`[data-tab-target="${CSS.escape(initialTab)}"]`)?.click();

  byAll("[data-copy]").forEach((button) => button.addEventListener("click", async () => {
    await navigator.clipboard?.writeText(button.dataset.copy);
    const old = button.textContent;
    button.textContent = "Kopiert ✓";
    setTimeout(() => { button.textContent = old; }, 1600);
  }));

  const pseudoQr = (container) => {
    const seed = container.dataset.qr || "apluspay";
    let hash = 2166136261;
    for (const char of seed) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619);
    for (let i = 0; i < 121; i += 1) {
      hash ^= hash << 13; hash ^= hash >>> 17; hash ^= hash << 5;
      const cell = document.createElement("span");
      const row = Math.floor(i / 11), col = i % 11;
      const finder = (row < 3 && col < 3) || (row < 3 && col > 7) || (row > 7 && col < 3);
      if (finder || (hash & 1)) cell.className = "filled";
      container.appendChild(cell);
    }
  };
  byAll(".qr-grid[data-qr]").forEach(pseudoQr);

  if (matchMedia("(pointer:fine)").matches && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
    byAll(".tilt-card").forEach((card) => {
      card.addEventListener("pointermove", (event) => {
        const rect = card.getBoundingClientRect();
        const x = (event.clientX - rect.left) / rect.width - .5;
        const y = (event.clientY - rect.top) / rect.height - .5;
        const base = card.classList.contains("phone-shell") ? 4 : 0;
        card.style.transform = `perspective(1000px) rotateX(${-y * 7}deg) rotateY(${x * 9 + base}deg) translateY(-3px)`;
      });
      card.addEventListener("pointerleave", () => { card.style.transform = ""; });
    });
  }

  const observer = new IntersectionObserver((entries) => entries.forEach((entry) => {
    if (entry.isIntersecting) entry.target.classList.add("is-visible");
  }), { threshold: .12 });
  byAll(".interactive-card").forEach((card) => observer.observe(card));

  let scannerStream = null;
  const scannerView = document.querySelector("[data-scanner-view]");
  const scannerStatus = document.querySelector("[data-scanner-status]");
  const scannerInput = document.querySelector("#id_member_number");
  const stopScanner = () => {
    scannerStream?.getTracks().forEach((track) => track.stop());
    scannerStream = null;
    if (scannerView) scannerView.hidden = true;
  };
  document.querySelector("[data-stop-scanner]")?.addEventListener("click", stopScanner);
  document.querySelector("[data-start-scanner]")?.addEventListener("click", async () => {
    if (!scannerView || !scannerInput) return;
    if (!("BarcodeDetector" in window)) {
      scannerStatus.textContent = "QR-Scan wird von diesem Browser nicht unterstützt. Member-ID bitte eingeben.";
      scannerInput.focus();
      return;
    }
    try {
      scannerStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
      const video = scannerView.querySelector("video");
      video.srcObject = scannerStream;
      await video.play();
      scannerView.hidden = false;
      scannerStatus.textContent = "QR-Code in den Rahmen halten…";
      const detector = new BarcodeDetector({ formats: ["qr_code"] });
      const scan = async () => {
        if (!scannerStream) return;
        const codes = await detector.detect(video).catch(() => []);
        if (codes.length) {
          const raw = codes[0].rawValue || "";
          const member = raw.match(/\d{8}/)?.[0] || raw;
          scannerInput.value = member;
          scannerStatus.textContent = `Erkannt: ${member}`;
          stopScanner();
          scannerInput.dispatchEvent(new Event("change", { bubbles: true }));
          return;
        }
        requestAnimationFrame(scan);
      };
      scan();
    } catch (error) {
      scannerStatus.textContent = "Kamerazugriff nicht möglich. Member-ID bitte manuell eingeben.";
    }
  });

})();
