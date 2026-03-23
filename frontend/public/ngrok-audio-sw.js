/* global self, clients */
// Adds ngrok-skip-browser-warning to media <audio>/<video> GETs so the free-tier HTML interstitial is skipped.
self.addEventListener("install", (event) => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  let url;
  try {
    url = new URL(req.url);
  } catch {
    return;
  }
  if (!url.hostname.includes("ngrok")) return;
  if (!url.pathname.includes("/stream/")) return;

  const headers = new Headers(req.headers);
  headers.set("ngrok-skip-browser-warning", "1");
  event.respondWith(
    fetch(new Request(req, { headers })).catch(() => fetch(req)),
  );
});
