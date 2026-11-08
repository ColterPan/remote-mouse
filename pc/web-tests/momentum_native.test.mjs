// Tests for momentum.js (fling physics) and native.js (Android-app bridge).
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { MOMENTUM_MAX_SPEED, Momentum, momentumStep } from '../remote_mouse/web/js/momentum.js';
import { NativeHost, nativeBridge } from '../remote_mouse/web/js/native.js';
import { SPEED_PRESETS, sanitizeSettings } from '../remote_mouse/web/js/settings.js';

// --- momentum ----------------------------------------------------------------

test('momentum distance is the same at 60 Hz and 120 Hz', () => {
  // Integer frame counter, so both runs end at exactly 400 ms.
  const run = (fps) => {
    const m = new Momentum();
    m.start(0, -0.05, 0);
    let total = 0;
    const frames = (400 * fps) / 1000;
    for (let i = 1; i <= frames; i += 1) total += m.step((i * 1000) / fps).dy;
    return total;
  };
  assert.ok(Math.abs(run(60) - run(120)) < 1e-6);
});

test('momentum slows down and stops by itself', () => {
  const m = new Momentum();
  m.start(0.03, 0, 0);
  const first = m.step(16).dx;
  let last = first;
  let t = 16;
  while (m.active && t < 10_000) {
    t += 16;
    last = m.step(t).dx;
  }
  assert.equal(m.active, false, 'stopped');
  assert.ok(last < first, 'slowed down');
  assert.ok(t < 3000, 'within a few seconds');
});

test('momentum is capped and can be stopped', () => {
  const m = new Momentum();
  m.start(99, -99, 0);
  assert.equal(m.vx, MOMENTUM_MAX_SPEED);
  assert.equal(m.vy, -MOMENTUM_MAX_SPEED);
  m.stop();
  assert.deepEqual(m.step(100), { dx: 0, dy: 0 });
});

test('momentumStep integrates exactly', () => {
  const { v, delta } = momentumStep(1, 325, 325);
  assert.ok(Math.abs(v - Math.exp(-1)) < 1e-9);
  assert.ok(Math.abs(delta - 325 * (1 - Math.exp(-1))) < 1e-9);
});

// --- settings presets --------------------------------------------------------

test('speed presets are valid sensitivities and momentum defaults on', () => {
  for (const value of Object.values(SPEED_PRESETS)) {
    assert.equal(sanitizeSettings({ sensitivity: value }).sensitivity, value);
  }
  assert.equal(sanitizeSettings({}).momentum, true);
  assert.equal(sanitizeSettings({ momentum: false }).momentum, false);
});

// --- native bridge -----------------------------------------------------------

function fakeBridge() {
  const sent = [];
  const bridge = {
    postMessage: (text) => sent.push(JSON.parse(text)),
    deliver(message) {
      bridge.onmessage({ data: JSON.stringify(message) });
    },
  };
  return { bridge, sent };
}

test('no bridge in a normal browser', () => {
  assert.equal(nativeBridge(), null);
});

test('NativeSocket behaves like a WebSocket for connection.js', () => {
  const { bridge, sent } = fakeBridge();
  const host = new NativeHost(bridge);
  const socket = host.openSocket('pc-1');
  assert.deepEqual(sent.at(-1), { op: 'connect', id: 'pc-1', cid: socket.cid });

  const events = [];
  socket.addEventListener('open', () => events.push('open'));
  socket.addEventListener('message', (e) => events.push(`message:${e.data}`));
  socket.addEventListener('close', (e) => events.push(`close:${e.code}`));

  bridge.deliver({ ev: 'open', cid: socket.cid, data: '{"t":"hello"}' });
  assert.equal(socket.readyState, 1);
  socket.send('{"t":"auth","token":"x","v":1}'); // swallowed: the app logs in itself
  socket.send('{"t":"move","dx":1,"dy":2}');
  assert.deepEqual(sent.at(-1), { op: 'send', msg: '{"t":"move","dx":1,"dy":2}' });
  assert.equal(sent.filter((m) => m.op === 'send').length, 1);

  bridge.deliver({ ev: 'close', cid: socket.cid, code: 1006 });
  assert.deepEqual(events, ['open', 'message:{"t":"hello"}', 'close:1006']);
  assert.equal(socket.readyState, 3);
});

test('events from an older connection attempt are ignored', () => {
  const { bridge } = fakeBridge();
  const host = new NativeHost(bridge);
  const old = host.openSocket('pc-1');
  const current = host.openSocket('pc-1');
  let closed = false;
  current.addEventListener('close', () => {
    closed = true;
  });
  bridge.deliver({ ev: 'close', cid: old.cid, code: 1006 });
  assert.equal(closed, false);
  assert.equal(current.readyState, 0);
});

test('an unknown PC is reported as "needs pairing" (4401)', () => {
  const { bridge } = fakeBridge();
  const host = new NativeHost(bridge);
  const socket = host.openSocket('gone');
  let code = 0;
  socket.addEventListener('close', (e) => {
    code = e.code;
  });
  bridge.deliver({ ev: 'close', cid: socket.cid, code: 4404 });
  assert.equal(code, 4401);
});

test('closing asks the app to disconnect; other events reach listeners', () => {
  const { bridge, sent } = fakeBridge();
  const host = new NativeHost(bridge);
  const seen = [];
  host.on('pcs', (e) => seen.push(e.pcs.length));
  bridge.deliver({ ev: 'pcs', pcs: [{ id: 'a' }], lastId: 'a' });
  bridge.deliver('not json'); // ignored safely
  const socket = host.openSocket('a');
  socket.close();
  socket.close(); // twice is harmless
  assert.deepEqual(seen, [1]);
  assert.equal(sent.filter((m) => m.op === 'disconnect').length, 1);
});
