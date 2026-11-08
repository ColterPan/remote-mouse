// Tests for textdiff.js, settings.js and connection.js helpers.
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { backoffDelay } from '../remote_mouse/web/js/connection.js';
import { DEFAULT_SETTINGS, sanitizeSettings, tokenFromHash } from '../remote_mouse/web/js/settings.js';
import { diffText } from '../remote_mouse/web/js/textdiff.js';

test('typing a character is an insert', () => {
  assert.deepEqual(diffText('​hel', '​help'), { deleteCount: 0, insert: 'p' });
});

test('backspace on the sentinel is one delete', () => {
  assert.deepEqual(diffText('​', ''), { deleteCount: 1, insert: '' });
});

test('autocorrect replacing a word becomes deletes + insert', () => {
  assert.deepEqual(diffText('teh', 'the'), { deleteCount: 2, insert: 'he' });
});

test('emoji count as a single character', () => {
  assert.deepEqual(diffText('a😀', 'a'), { deleteCount: 1, insert: '' });
  assert.deepEqual(diffText('a😀', 'a😃'), { deleteCount: 1, insert: '😃' });
});

test('settings: unknown keys dropped, ranges enforced, wrong types ignored', () => {
  const s = sanitizeSettings({ sensitivity: 99, scrollSpeed: 'fast', haptics: false, evil: 1 });
  assert.equal(s.sensitivity, 4);
  assert.equal(s.scrollSpeed, DEFAULT_SETTINGS.scrollSpeed);
  assert.equal(s.haptics, false);
  assert.equal('evil' in s, false);
  assert.ok(Object.isFrozen(s));
});

test('settings: garbage input gives defaults', () => {
  assert.deepEqual({ ...sanitizeSettings(null) }, { ...DEFAULT_SETTINGS });
  assert.deepEqual({ ...sanitizeSettings('x') }, { ...DEFAULT_SETTINGS });
});

test('token is read from the URL fragment and validated', () => {
  const token = 'AbCdEfGhIjKlMnOpQrStUv';
  assert.equal(tokenFromHash(`#t=${token}&fp=abc`), token);
  assert.equal(tokenFromHash('#t=short'), null);
  assert.equal(tokenFromHash('#t=<script>alert(1)</script>xxxxxxxxxxxxx'), null);
  assert.equal(tokenFromHash(''), null);
});

test('reconnect backoff grows then caps', () => {
  assert.equal(backoffDelay(0), 500);
  assert.equal(backoffDelay(1), 1000);
  assert.equal(backoffDelay(50), 5000);
});
