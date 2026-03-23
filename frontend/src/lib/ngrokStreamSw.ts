/** Registers SW that injects ngrok-skip-browser-warning on /stream/* GETs (true streaming vs full blob). */
let registrationPromise: Promise<ServiceWorkerRegistration | null> | null = null;

export function shouldUseNgrokStreamSw(): boolean {
  if (typeof window === "undefined") return false;
  if (!import.meta.env.PROD) return false;
  if (!("serviceWorker" in navigator)) return false;
  return /ngrok/i.test((import.meta.env.VITE_API_BASE_URL || "").trim());
}

export async function ensureNgrokStreamSw(): Promise<boolean> {
  if (!shouldUseNgrokStreamSw()) return false;

  if (!registrationPromise) {
    const scopeUrl = new URL(import.meta.env.BASE_URL || "/", window.location.origin).href;
    const swUrl = new URL("ngrok-audio-sw.js", scopeUrl).href;
    registrationPromise = navigator.serviceWorker
      .register(swUrl, { scope: scopeUrl, updateViaCache: "none" })
      .catch(() => null);
  }

  const reg = await registrationPromise;
  if (!reg) return false;

  await navigator.serviceWorker.ready;

  if (navigator.serviceWorker.controller) return true;

  await new Promise<void>((resolve) => {
    const done = () => resolve();
    navigator.serviceWorker.addEventListener("controllerchange", done, { once: true });
    setTimeout(done, 3500);
  });

  return !!navigator.serviceWorker.controller;
}
