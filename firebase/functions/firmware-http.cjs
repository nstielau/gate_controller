const {hash} = require("./administration.cjs");
// Device authentication is separate from browser Google/App Check callables.
function createFirmwareHandler(deviceService, bucket) {
  return async (req, res) => {
  res.set("Cache-Control", "no-store");
  try {
    const route = req.path.split("/").filter(Boolean).pop();
    if (!((req.method === "GET" && ["manifest", "artifact"].includes(route)) ||
          (req.method === "POST" && route === "report"))) return res.status(404).end();
    if (req.rawBody?.length > 4096) return res.status(413).end();
    const id = req.get("X-Device-ID");
    const token = /^Bearer ([a-f0-9]{64})$/.exec(req.get("Authorization") || "")?.[1];
    const device = await deviceService.authorize(id, token, route);
    if (route === "report") {
      await deviceService.report(id, req.body);
      return res.status(204).end();
    }
    const manifest = await deviceService.manifest(device);
    if (!manifest) return res.status(204).end();
    if (route === "manifest") return res.json(manifest);
    if (req.query.sequence !== String(manifest.sequence)) return res.status(409).end();
    const file = bucket.file(manifest.artifact_object);
    const [meta] = await file.getMetadata();
    if (Number(meta.size) !== manifest.size) throw new Error("Artifact size mismatch");
    const [bytes] = await file.download({validation: "crc32c"});
    if (bytes.length !== manifest.size || hash(bytes) !== manifest.sha256) throw new Error("Artifact digest mismatch");
    res.set("Content-Type", "application/octet-stream");
    return res.send(bytes);
  } catch (error) {
    const status = {unauthenticated: 401, "resource-exhausted": 429, "invalid-argument": 400}[error.publicCode] || 503;
    // Never log request headers, tokens, or Storage signed URLs.
    console.error("Firmware request failed", {status});
    return res.status(status).json({error: "firmware_request_failed"});
  }
  };
}
module.exports = {createFirmwareHandler};
