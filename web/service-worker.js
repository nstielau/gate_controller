// Build replaces these constants with a content-based release and hashed assets.
const CACHE = "drawbridge-__RELEASE__";
const ASSETS = __ASSETS__;
const allowed = new Set(ASSETS);
self.addEventListener("install", event => event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS))));
self.addEventListener("message", event => { if (event.data === "activate") self.skipWaiting(); });
self.addEventListener("activate", event => event.waitUntil(
  caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith("drawbridge-") && key !== CACHE).map(key => caches.delete(key))))
));
self.addEventListener("fetch", event => {
  const url = new URL(event.request.url);
  // Never intercept auth helpers, APIs, POSTs, or external requests; never queue commands.
  if (event.request.method !== "GET" || url.origin !== self.location.origin || !allowed.has(url.pathname)) return;
  event.respondWith(caches.open(CACHE).then(async cache => (await cache.match(url.pathname)) || fetch(event.request)));
});
