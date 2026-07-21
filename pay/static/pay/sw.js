const CACHE = "apluspay-central-v2";
const CORE = ["/", "/dashboard/", "/vendors/", "/static/pay/app.css", "/static/pay/app.js", "/static/pay/icon.svg"];
self.addEventListener("install", (event) => event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(CORE)).catch(() => null)));
self.addEventListener("activate", (event) => event.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))));
self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  event.respondWith(fetch(event.request).then((response) => {
    const clone = response.clone(); caches.open(CACHE).then((cache) => cache.put(event.request, clone)); return response;
  }).catch(() => caches.match(event.request).then((cached) => cached || caches.match("/"))));
});
