/**
 * keyboard.js — Typing, special keys, sticky modifiers and shortcut buttons.
 *
 * Typing with the phone's own keyboard:
 *   A hidden <input> is focused to bring up the soft keyboard. We keep a
 *   single invisible character (a zero-width space, the SENTINEL) in it, so
 *   that pressing Backspace on an "empty" field still produces a change we
 *   can see. After every change we compare old vs new value (textdiff.js),
 *   send backspaces / text to the PC, then reset the field to the sentinel.
 *   While the keyboard is "composing" a word (underlined suggestion) we must
 *   not touch the field, or the keyboard gets confused — so we wait for
 *   compositionend before resetting.
 *
 * Sticky modifiers (Ctrl, Alt, Shift, Win):
 *   Tap Ctrl → it lights up → the next key you press (a button, or a letter
 *   typed on the phone keyboard) is sent as Ctrl+that key, then Ctrl turns
 *   off. Tap a lit modifier again to cancel it.
 */

import { diffText } from './textdiff.js';

const SENTINEL = '​';
const MAX_TEXT_CHUNK = 400; // stay under the PC's 500-character limit
const SHORTCUT_CHAR = /^[a-z0-9]$/;
const MODIFIER_ORDER = ['ctrl', 'alt', 'shift', 'win'];

// Browser key names → protocol key names (for hardware keyboards and the
// few keys phone keyboards do report properly, like Enter).
const KEY_NAMES = {
  Enter: 'enter', Tab: 'tab', Escape: 'esc',
  ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right',
  Delete: 'delete', Insert: 'insert', Home: 'home', End: 'end',
  PageUp: 'page_up', PageDown: 'page_down',
  ...Object.fromEntries(Array.from({ length: 12 }, (_, i) => [`F${i + 1}`, `f${i + 1}`])),
};

/** Split long pasted text into chunks without breaking emoji in half. */
function chunks(text) {
  const chars = Array.from(text);
  const result = [];
  for (let i = 0; i < chars.length; i += MAX_TEXT_CHUNK) {
    result.push(chars.slice(i, i + MAX_TEXT_CHUNK).join(''));
  }
  return result;
}

/**
 * @param {object} opts
 * @param {HTMLInputElement} opts.input
 * @param {(msg: object) => void} opts.send
 * @param {() => void} opts.haptic
 */
export function createKeyboard({ input, send, haptic }) {
  let armed = [];
  let last = SENTINEL;
  let composing = false;
  const modButtons = Array.from(document.querySelectorAll('[data-mod]'));

  function renderModifiers() {
    for (const button of modButtons) {
      const on = armed.includes(button.dataset.mod);
      button.classList.toggle('armed', on);
      button.setAttribute('aria-pressed', String(on));
    }
  }

  /** Use up the armed modifiers (plus any extra ones) for one key press. */
  function takeModifiers(extra = []) {
    const combined = MODIFIER_ORDER.filter((m) => armed.includes(m) || extra.includes(m));
    if (armed.length) {
      armed = [];
      renderModifiers();
    }
    return combined;
  }

  function sendKey(key, extraMods = []) {
    send({ t: 'key', k: key, mods: takeModifiers(extraMods) });
  }

  function sendText(text) {
    if (!text) return;
    const lower = text.toLowerCase();
    if (armed.length && SHORTCUT_CHAR.test(lower)) {
      sendKey(lower); // e.g. Ctrl armed + typed "c" → Ctrl+C
      return;
    }
    if (armed.length) takeModifiers(); // modifiers don't apply to plain text
    for (const part of chunks(text)) send({ t: 'text', s: part });
  }

  function resetField() {
    input.value = SENTINEL;
    last = SENTINEL;
  }

  function sync() {
    const current = input.value;
    const { deleteCount, insert } = diffText(last, current);
    last = current;
    for (let i = 0; i < deleteCount; i += 1) send({ t: 'key', k: 'backspace', mods: [] });
    sendText(insert);
    if (!composing && current !== SENTINEL) resetField();
  }

  input.addEventListener('input', sync);
  input.addEventListener('compositionstart', () => {
    composing = true;
  });
  input.addEventListener('compositionend', () => {
    composing = false;
    sync();
  });

  input.addEventListener('keydown', (e) => {
    // 229 = "the soft keyboard is handling this"; the input event will tell us.
    if (e.isComposing || e.keyCode === 229) return;
    const held = [e.ctrlKey && 'ctrl', e.altKey && 'alt', e.metaKey && 'win'].filter(Boolean);
    const name = KEY_NAMES[e.key];
    if (name) {
      e.preventDefault();
      sendKey(name, e.shiftKey ? [...held, 'shift'] : held);
      return;
    }
    const lower = e.key.length === 1 ? e.key.toLowerCase() : '';
    if (held.length && SHORTCUT_CHAR.test(lower)) {
      e.preventDefault(); // hardware keyboard shortcut like Ctrl+S
      sendKey(lower, e.shiftKey ? [...held, 'shift'] : held);
    }
  });

  // On-screen key buttons, shortcut chips and media buttons.
  for (const button of document.querySelectorAll('[data-key]')) {
    button.addEventListener('click', () => {
      const mods = (button.dataset.mods || '').split(',').filter(Boolean);
      sendKey(button.dataset.key, mods);
      haptic();
    });
  }

  for (const button of modButtons) {
    button.addEventListener('click', () => {
      const mod = button.dataset.mod;
      armed = armed.includes(mod) ? armed.filter((m) => m !== mod) : [...armed, mod];
      renderModifiers();
      haptic();
    });
  }

  return {
    open() {
      resetField();
      input.focus({ preventScroll: true });
    },
    close() {
      input.blur();
    },
  };
}
