// Firebase's provisioned Google OAuth client accepts this Hosting callback.
// Keep the page and auth helper on the same origin for Safari storage access.
export const AUTH_DOMAIN = "drawbridge-45487.firebaseapp.com";
export function canonicalAppUrl(href) {
  const url = new URL(href);
  if (url.hostname === AUTH_DOMAIN) return null;
  if (!["drawbridge-45487.web.app", "drawbridge.stielau.us"].includes(url.hostname)) {
    throw new Error("Unsupported app origin");
  }
  url.protocol = "https:";
  url.host = AUTH_DOMAIN;
  return url.href;
}
