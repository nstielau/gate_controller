// Project stored, authenticated reports into public administrative metadata.
const KNOWN_BOARDS = new Set(["seeed_xiao_esp32_s3_sense", "adafruit_feather_esp32s3_reverse_tft"]);
const knownBoard = value => typeof value === "string" && KNOWN_BOARDS.has(value) ? value : null;
const VERSION = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/;
const version = value => typeof value === "string" && VERSION.test(value) ? value : null;
const timestamp = value => Number.isSafeInteger(value) && value > 0 && value <= 8640000000000000 ? value : null;
const lastSeen = (...values) => Math.max(0, ...values.map(value => timestamp(value) || 0)) || null;
function observation(device) {
  const maintenance = device.maintenance, reported = device.reportedFirmware;
  const snapshots = [
    {appVersion: version(maintenance?.appVersion), baseVersion: version(maintenance?.baseVersion), boardId: knownBoard(maintenance?.boardId), atMs: timestamp(maintenance?.lastSeenAtMs)},
    {appVersion: version(reported?.version), baseVersion: version(reported?.base_version), boardId: knownBoard(reported?.board_id), atMs: timestamp(reported?.atMs)},
  ].filter(snapshot => snapshot.atMs !== null).sort((a, b) => b.atMs - a.atMs);
  const latest = snapshots[0];
  return {
    lastSeenAtMs: lastSeen(device.lastSeenAtMs, maintenance?.lastSeenAtMs, reported?.atMs),
    appVersion: latest?.appVersion || null,
    baseVersion: latest?.baseVersion || null,
    boardId: latest?.boardId || null,
    reportedAtMs: latest?.atMs || null,
  };
}
function publicReport(value) {
  if (!value || !["current", "trial", "rolled_back", "error", "disabled"].includes(value.state) || !version(value.version)) return null;
  return {state: value.state, version: version(value.version), base_version: version(value.base_version),
    sequence: Number.isSafeInteger(value.sequence) && value.sequence >= 0 ? value.sequence : null,
    reason: typeof value.reason === "string" && /^[a-z_]{1,40}$/.test(value.reason) ? value.reason : null,
    atMs: timestamp(value.atMs)};
}
module.exports = {observation, publicReport, lastSeen, knownBoard};
