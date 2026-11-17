const {test} = require('node:test');
const assert = require('node:assert/strict');
const pairing = () => import('../pairing.mjs');
const code = 'a'.repeat(64);
function storage(value) {
  return {value, getItem() { return this.value ?? null; }, setItem(_key, next) { this.value = next; }, removeItem() { this.value = null; }};
}
test('captures a valid QR and removes its fragment before continuing', async () => {
  const {capturePairingIntent} = await pairing();
  const saved = storage(); const replaced = [];
  assert.deepEqual(capturePairingIntent({href: `https://drawbridge-45487.firebaseapp.com/?device_id=AB12CD#pair=${code}`, storage: saved, now: 100, replace: url => replaced.push(url)}), {deviceId: 'ab12cd', pairingCode: code, createdAtMs: 100});
  assert.deepEqual(replaced, ['https://drawbridge-45487.firebaseapp.com/?device_id=AB12CD']);
  assert.equal(JSON.parse(saved.value).pairingCode, code);
});
test('restores a scan when OAuth returns without a query', async () => {
  const {capturePairingIntent} = await pairing();
  const saved = storage(JSON.stringify({deviceId: 'ab12cd', pairingCode: code, createdAtMs: 100}));
  assert.equal(capturePairingIntent({href: 'https://drawbridge-45487.firebaseapp.com/', storage: saved, now: 200}).deviceId, 'ab12cd');
});
test('malformed, expired, and future session intents cannot register', async () => {
  const {capturePairingIntent} = await pairing();
  for (const value of ['{', '{}', JSON.stringify({deviceId: 'ab12cd', pairingCode: code, createdAtMs: 0}), JSON.stringify({deviceId: 'ab12cd', pairingCode: code, createdAtMs: 9000000})]) {
    const saved = storage(value);
    assert.equal(capturePairingIntent({href: 'https://drawbridge-45487.firebaseapp.com/', storage: saved, now: 7200001}), null);
    assert.equal(saved.value, null);
  }
});
test('a malformed new scan clears an old valid intent and strips its fragment', async () => {
  const {capturePairingIntent} = await pairing();
  const saved = storage(JSON.stringify({deviceId: 'ab12cd', pairingCode: code, createdAtMs: 100})); const replaced = [];
  assert.equal(capturePairingIntent({href: 'https://drawbridge-45487.firebaseapp.com/?device_id=other#pair=bad', storage: saved, now: 200, replace: url => replaced.push(url)}), null);
  assert.equal(saved.value, null);
  assert.equal(replaced.length, 1);
});
test('a scan without its pairing code never reuses a previous device proof', async () => {
  const {capturePairingIntent} = await pairing();
  const saved = storage(JSON.stringify({deviceId: 'ab12cd', pairingCode: code, createdAtMs: 100}));
  assert.equal(capturePairingIntent({href: 'https://drawbridge-45487.firebaseapp.com/?device_id=other', storage: saved, now: 200}), null);
});
test('compact QR parameters carry the same device proof', async () => {
  const {capturePairingIntent} = await pairing();
  const saved = storage();
  assert.deepEqual(capturePairingIntent({href: `https://drawbridge-45487.firebaseapp.com/?d=AB12CD#p=${code}`, storage: saved, now: 100, replace() {}}), {deviceId: 'ab12cd', pairingCode: code, createdAtMs: 100});
});
test('a reload after stripping the fragment restores the matching saved scan', async () => {
  const {capturePairingIntent} = await pairing();
  const saved = storage(JSON.stringify({deviceId: 'ab12cd', pairingCode: code, createdAtMs: 100}));
  assert.equal(capturePairingIntent({href: 'https://drawbridge-45487.firebaseapp.com/?device_id=ab12cd', storage: saved, now: 200})?.pairingCode, code);
});
