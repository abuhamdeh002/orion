self.addEventListener("install", (event) => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("message", (event) => {
  const text = event.data && event.data.text;
  if (!text || !self.registration.showNotification) return;
  self.registration.showNotification("ORION", { body: text });
});
