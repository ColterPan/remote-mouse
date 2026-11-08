// Unit tests for the phone remote's gesture logic. Run:  node --test "web-tests/*.test.mjs"
import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  DOUBLE_TAP_MS,
  GestureTracker,
  TAP_MAX_MS,
  panToScroll,
  pointerGain,
} from '../remote_mouse/web/js/gestures.js';

const types = (actions) => actions.map((a) => a.type);
const LEFT = { type: 'click', button: 'left' };

/** A quick one-finger tap at (x, y) starting at time t. */
function tap(g, t, x = 100, y = 100, id = 1) {
  return [...g.down(id, x, y, t), ...g.up(id, x, y, t + 60)];
}

test('slow movement uses the plain sensitivity, fast movement is boosted', () => {
  assert.equal(pointerGain(0.05, 2), 2);
  assert.ok(pointerGain(1.5, 2) > 2);
  assert.equal(pointerGain(100, 1), pointerGain(50, 1), 'boost is capped');
});

test('natural scrolling: fingers up scrolls the page down', () => {
  const s = panToScroll(0, -36, { naturalScroll: true, scrollSpeed: 1 });
  assert.equal(s.dy, -1);
  const t = panToScroll(0, -36, { naturalScroll: false, scrollSpeed: 1 });
  assert.equal(t.dy, 1);
});

test('one-finger tap is a left click, released after the double-tap window', () => {
  const g = new GestureTracker();
  assert.deepEqual(tap(g, 0), []); // held back: a drag might follow
  assert.equal(g.hasPendingClick, true);
  assert.deepEqual(g.expire(60 + DOUBLE_TAP_MS - 1), []); // too early
  assert.deepEqual(g.expire(60 + DOUBLE_TAP_MS), [LEFT]);
  assert.equal(g.hasPendingClick, false);
  assert.deepEqual(g.expire(10_000), [], 'only once');
});

test('two quick taps are a double-click', () => {
  const g = new GestureTracker();
  tap(g, 0);
  assert.deepEqual(tap(g, 150, 102, 100), [LEFT, LEFT]);
  assert.equal(g.hasPendingClick, false);
});

test('tap, then touch again and slide → drag starting exactly where you tapped', () => {
  const g = new GestureTracker();
  tap(g, 0);
  assert.deepEqual(g.down(2, 105, 102, 150), []);
  assert.deepEqual(g.move(2, 110, 102, 170), [], 'small moves are held back');
  const start = g.move(2, 130, 102, 200);
  assert.deepEqual(types(start), ['down', 'move'], 'button goes down BEFORE moving');
  assert.ok(start[1].dx >= 25, 'held-back movement is delivered after the press');
  assert.equal(g.isDragging, true);
  assert.deepEqual(types(g.move(2, 160, 110, 230)), ['move']);
  assert.deepEqual(g.up(2, 160, 110, 900), [{ type: 'up', button: 'left' }]);
  assert.equal(g.isDragging, false);
  assert.deepEqual(g.expire(10_000), [], 'no stray click after a drag');
});

test('a second touch that comes too late sends the first click, then moves normally', () => {
  const g = new GestureTracker();
  tap(g, 0);
  assert.deepEqual(g.down(1, 100, 100, 60 + DOUBLE_TAP_MS + 100), [LEFT]);
  assert.deepEqual(types(g.move(1, 150, 100, 600)), ['move']);
});

test('a second touch far away sends the first click and is not a drag', () => {
  const g = new GestureTracker();
  tap(g, 0);
  assert.deepEqual(g.down(1, 300, 300, 150), [LEFT]);
  assert.deepEqual(types(g.move(1, 340, 300, 200)), ['move']);
});

test('tap, then a long press: the first click is still delivered', () => {
  const g = new GestureTracker();
  tap(g, 0);
  g.down(1, 100, 100, 150);
  assert.deepEqual(g.up(1, 100, 100, 150 + TAP_MAX_MS + 100), [LEFT]);
});

test('tap, then a two-finger tap: left click then right click', () => {
  const g = new GestureTracker();
  tap(g, 0);
  g.down(1, 100, 100, 150);
  g.down(2, 150, 100, 155);
  g.up(1, 100, 100, 200);
  assert.deepEqual(g.up(2, 150, 100, 205), [LEFT, { type: 'click', button: 'right' }]);
});

test('two-finger tap is a right click, three-finger tap a middle click (no delay)', () => {
  const g = new GestureTracker();
  g.down(1, 100, 100, 0);
  g.down(2, 150, 100, 10);
  assert.deepEqual(g.up(1, 100, 100, 90), []); // waits for the last finger
  assert.deepEqual(g.up(2, 150, 100, 100), [{ type: 'click', button: 'right' }]);

  g.down(1, 100, 100, 1000);
  g.down(2, 150, 100, 1005);
  g.down(3, 200, 100, 1010);
  g.up(1, 100, 100, 1080);
  g.up(2, 150, 100, 1085);
  assert.deepEqual(g.up(3, 200, 100, 1090), [{ type: 'click', button: 'middle' }]);
});

test('a long press is not a click', () => {
  const g = new GestureTracker();
  g.down(1, 100, 100, 0);
  assert.deepEqual(g.up(1, 100, 100, TAP_MAX_MS + 50), []);
  assert.equal(g.hasPendingClick, false);
});

test('sliding one finger moves the pointer and is not a click', () => {
  const g = new GestureTracker({ sensitivity: 1 });
  g.down(1, 100, 100, 0);
  const actions = g.move(1, 110, 95, 100);
  assert.equal(actions.length, 1);
  assert.equal(actions[0].type, 'move');
  assert.ok(actions[0].dx >= 10 && actions[0].dy <= -5);
  g.move(1, 150, 95, 150);
  assert.deepEqual(g.up(1, 150, 95, 200), []);
  assert.equal(g.hasPendingClick, false);
});

test('two-finger slide scrolls and does not move the pointer', () => {
  const g = new GestureTracker({ naturalScroll: true, scrollSpeed: 1 });
  g.down(1, 100, 200, 0);
  g.down(2, 150, 200, 5);
  const actions = [...g.move(1, 100, 128, 50), ...g.move(2, 150, 128, 55)];
  assert.deepEqual(types(actions), ['scroll', 'scroll']);
  const total = actions.reduce((sum, a) => sum + a.dy, 0);
  // Both fingers 72px up → the midpoint moves 72px → 72 / 36 = 2 notches down.
  assert.equal(total, -2);
});

test('lifting one finger after scrolling does not jump the pointer', () => {
  const g = new GestureTracker();
  g.down(1, 100, 200, 0);
  g.down(2, 150, 200, 5);
  g.move(1, 100, 150, 50);
  g.up(2, 150, 150, 60);
  assert.deepEqual(g.move(1, 100, 100, 70), []);
});

test('cancel during a drag releases the button and forgets pending clicks', () => {
  const g = new GestureTracker();
  tap(g, 0);
  g.down(1, 100, 100, 150);
  g.move(1, 140, 100, 200);
  assert.deepEqual(g.cancel(), [{ type: 'up', button: 'left' }]);
  assert.deepEqual(g.cancel(), []);
  tap(g, 1000);
  g.cancel();
  assert.equal(g.hasPendingClick, false);
});

test('events for unknown pointers are ignored', () => {
  const g = new GestureTracker();
  assert.deepEqual(g.move(9, 1, 1, 1), []);
  assert.deepEqual(g.up(9, 1, 1, 1), []);
});
