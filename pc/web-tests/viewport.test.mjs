// Tests for viewport.js: detecting the phone keyboard from viewport sizes.
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { KEYBOARD_MIN_PX, nextViewport } from '../remote_mouse/web/js/viewport.js';

const PORTRAIT = { width: 412, height: 915 };

test('first measurement is the baseline, keyboard closed', () => {
  const s = nextViewport(null, PORTRAIT);
  assert.equal(s.baseline, 915);
  assert.equal(s.keyboardOpen, false);
});

test('a big height loss at the same width means the keyboard opened', () => {
  const open = nextViewport(nextViewport(null, PORTRAIT), { width: 412, height: 560 });
  assert.equal(open.keyboardOpen, true);
  assert.equal(open.baseline, 915);
  const closed = nextViewport(open, PORTRAIT);
  assert.equal(closed.keyboardOpen, false);
});

test('small changes (browser toolbar hiding) are not a keyboard', () => {
  const s = nextViewport(nextViewport(null, PORTRAIT), { width: 412, height: 915 - KEYBOARD_MIN_PX + 10 });
  assert.equal(s.keyboardOpen, false);
});

test('the baseline grows to the tallest height seen', () => {
  let s = nextViewport(null, { width: 412, height: 860 }); // toolbar shown
  s = nextViewport(s, PORTRAIT); // toolbar hidden
  assert.equal(s.baseline, 915);
  s = nextViewport(s, { width: 412, height: 600 });
  assert.equal(s.keyboardOpen, true);
});

test('rotating the phone starts a new baseline', () => {
  let s = nextViewport(null, PORTRAIT);
  s = nextViewport(s, { width: 915, height: 412 });
  assert.equal(s.baseline, 412);
  assert.equal(s.keyboardOpen, false);
  s = nextViewport(s, { width: 915, height: 180 }); // keyboard in landscape
  assert.equal(s.keyboardOpen, true);
});

test('repeated open/close toggles stay consistent', () => {
  let s = nextViewport(null, PORTRAIT);
  for (let i = 0; i < 10; i += 1) {
    s = nextViewport(s, { width: 412, height: 540 });
    assert.equal(s.keyboardOpen, true);
    s = nextViewport(s, PORTRAIT);
    assert.equal(s.keyboardOpen, false);
  }
});

test('portrait phone with the keyboard open stays portrait (the squashed-touchpad bug)', () => {
  // 360×640 phone: with the keyboard up, only 360×350 is visible: wider than tall.
  let s = nextViewport(null, { width: 360, height: 640 });
  s = nextViewport(s, { width: 360, height: 350 });
  assert.equal(s.keyboardOpen, true);
  assert.equal(s.landscape, false);
});

test('a phone turned sideways is landscape; a tablet is not', () => {
  assert.equal(nextViewport(null, { width: 915, height: 412 }).landscape, true);
  assert.equal(nextViewport(null, { width: 1280, height: 800 }).landscape, false);
  assert.equal(nextViewport(null, { width: 412, height: 915 }).landscape, false);
});
