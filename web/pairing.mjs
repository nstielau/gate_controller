// This is a derived pairing proof, never the device's private secret.
export const PAIRING_STORAGE_KEY = "drawbridge.pairing";
export const PAIRING_MAX_AGE_MS = 2 * 60 * 60 * 1000;
export function validPairingIntent(value, now = Date.now()) {
  return !!value && typeof value.deviceId === "string" && typeof value.pairingCode === "string"
    && /^[a-z0-9-]{1,64}$/.test(value.deviceId)
    && /^[a-f0-9]{64}$/.test(value.pairingCode)
    && Number.isSafeInteger(value.createdAtMs) && value.createdAtMs <= now
    && now - value.createdAtMs < PAIRING_MAX_AGE_MS;
}
export function savePairingIntent(storage, intent) {
  try {
    if (intent) storage.setItem(PAIRING_STORAGE_KEY, JSON.stringify(intent));
    else storage.removeItem(PAIRING_STORAGE_KEY);
  } catch { /* Private browsing may restrict storage; this page can still register. */ }
}
export function capturePairingIntent({href, storage, now = Date.now(), replace = () => {}}) {
  const url = new URL(href);
  let saved;
  try { saved = JSON.parse(storage.getItem(PAIRING_STORAGE_KEY)); } catch { saved = null; }
  const fragment = new URLSearchParams(url.hash.slice(1));
  const isScan = url.searchParams.has("device_id") || url.searchParams.has("d") || fragment.has("pair") || fragment.has("p");
  if (isScan) {
    const intent = {
      deviceId: (url.searchParams.get("device_id") || url.searchParams.get("d") || "").trim().toLowerCase(),
      pairingCode: fragment.get("pair") || fragment.get("p") || "",
      createdAtMs: now
    };
    if (!url.hash && saved?.deviceId === intent.deviceId && validPairingIntent(saved, now)) return saved;
    // Strip immediately, including malformed proofs, before auth or API initialization.
    if (url.hash) { url.hash = ""; replace(url.href); }
    const next = validPairingIntent(intent, now) ? intent : null;
    savePairingIntent(storage, next);
    return next;
  }
  if (validPairingIntent(saved, now)) return saved;
  savePairingIntent(storage, null);
  return null;
}
