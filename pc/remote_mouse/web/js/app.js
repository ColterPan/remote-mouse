/**
 * app.js — Starts the phone remote and wires all the pieces together.
 *
 *   settings.js   preferences + pairing token (localStorage)
 *   connection.js the WebSocket to the PC (auto-reconnect)
 *   touchpad.js   touchpad + scroll strip
 *   keyboard.js   typing, special keys, shortcuts, media keys
 *
 * Pairing: the QR code opens https://<pc>:8765/#t=<token>. We read the token
 * from the "#…" part, save it, and immediately remove it from the address bar
 * so it isn't visible or accidentally shared. When you open the home-screen
 * icon later, the saved token is used.
 */

import { Connection } from './connection.js';
import { createKeyboard } from './keyboard.js';
import {
  forgetToken,
  loadSettings,
  loadToken,
  saveSettings,
  saveToken,
  tokenFromHash,
} from './settings.js';
import { createTouchpad } from './touchpad.js';

const $ = (id) => document.getElementById(id);

let settings = loadSettings();
let token = readPairingToken();
let wakeLock = null;

function readPairingToken() {
  const fromHash = tokenFromHash(location.hash);
  if (fromHash) {
    saveToken(fromHash);
    history.replaceState(null, '', location.pathname); // hide the secret
  }
  return fromHash || loadToken();
}

const haptic = () => {
  if (settings.haptics) navigator.vibrate?.(12);
};

// --- Connection status ------------------------------------------------------

const statusEl = $('status');
const statusText = $('status-text');
const pairScreen = $('pair-screen');

const PAIR_REASONS = {
  missing: "This phone isn't paired yet.",
  rejected: 'The pairing code was not accepted — it may have been reset on the PC. Scan the QR code again.',
  forgotten: 'This phone forgot the PC. Scan the QR code to pair again.',
};

function showPairScreen(reason) {
  $('pair-reason').textContent = PAIR_REASONS[reason] || PAIR_REASONS.missing;
  pairScreen.hidden = false;
}

function onStatus(state, detail = {}) {
  statusEl.dataset.state = state;
  // The PC releases held buttons when a phone disconnects, so the lock is off.
  if (state !== 'connected') showDragLock(false);
  if (state === 'connected') {
    statusText.textContent = detail.name ? `Connected · ${detail.name}` : 'Connected';
    pairScreen.hidden = true;
  } else if (state === 'connecting') {
    statusText.textContent = 'Connecting…';
  } else if (state === 'unauthorized') {
    statusText.textContent = 'Not paired';
    showPairScreen(detail.reason);
  } else if (detail.reason === 'version') {
    statusText.textContent = 'Update the PC app and phone remote';
  } else {
    statusText.textContent = 'PC not reachable — retrying…';
  }
}

const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
const connection = new Connection({
  url: `${scheme}://${location.host}/ws`,
  getToken: () => token,
  onStatus,
});

// --- Drag lock: keeps the PC's left button held until tapped again ----------

const dragLock = $('drag-lock');
const isDragLocked = () => dragLock.getAttribute('aria-pressed') === 'true';
function showDragLock(on) {
  dragLock.setAttribute('aria-pressed', String(on));
}
function setDragLock(on) {
  if (isDragLocked() === on) return;
  showDragLock(on);
  connection.send({ t: on ? 'down' : 'up', b: 'left' });
}
dragLock.addEventListener('click', () => {
  setDragLock(!isDragLocked());
  haptic();
});

/** Send to the PC. Any left click/release also ends a drag lock on the PC,
 *  so keep the lock button's look in sync with reality. */
const send = (message) => {
  if (message.b === 'left' && (message.t === 'up' || message.t === 'click')) showDragLock(false);
  return connection.send(message);
};

// --- Touchpad & keyboard ----------------------------------------------------

const touchpad = createTouchpad({
  element: $('touchpad'),
  strip: $('scroll-strip'),
  hint: $('touchpad-hint'),
  send,
  getOptions: () => ({
    sensitivity: settings.sensitivity,
    scrollSpeed: settings.scrollSpeed,
    naturalScroll: settings.naturalScroll,
  }),
  onClick: haptic,
});

const keyboard = createKeyboard({ input: $('kb-input'), send, haptic });

// --- Mouse buttons: press = button down, release = button up ----------------
// This lets you hold "Left" with your thumb and drag with another finger.

const buttonReleasers = Array.from(document.querySelectorAll('[data-button]'), (button) => {
  const name = button.dataset.button;
  let pressed = false;
  const release = () => {
    if (!pressed) return;
    pressed = false;
    button.classList.remove('pressed');
    send({ t: 'up', b: name });
  };
  button.addEventListener('pointerdown', (e) => {
    e.preventDefault();
    button.setPointerCapture(e.pointerId);
    pressed = true;
    button.classList.add('pressed');
    send({ t: 'down', b: name });
    haptic();
  });
  button.addEventListener('pointerup', release);
  button.addEventListener('pointercancel', release);
  button.addEventListener('lostpointercapture', release);
  return release;
});

/** Let go of every on-screen mouse button (e.g. the app went to the background
 *  while you were holding one — the page may never see your finger lift). */
const releaseAllButtons = () => buttonReleasers.forEach((release) => release());

// Tapping buttons must not steal focus from the hidden text field, otherwise
// the phone keyboard would close every time you press a special key.
document.addEventListener('pointerdown', (e) => {
  if (e.target.closest('.panel, .toolbar, .mouse-buttons')) e.preventDefault();
});

// --- Toolbar panels (only one open at a time) -------------------------------

const panels = Array.from(document.querySelectorAll('.panel'));
const tools = Array.from(document.querySelectorAll('.tool'));
let openPanel = null;

function showPanel(id) {
  openPanel = id;
  for (const panel of panels) panel.hidden = panel.id !== id;
  for (const tool of tools) tool.classList.toggle('active', tool.dataset.panel === id);
  if (id === 'panel-keyboard') keyboard.open();
  else keyboard.close();
}

for (const tool of tools) {
  tool.addEventListener('click', () => {
    showPanel(openPanel === tool.dataset.panel ? null : tool.dataset.panel);
  });
}

// --- Settings dialog --------------------------------------------------------

const dialog = $('settings');
const fields = {
  sensitivity: $('sensitivity'),
  scrollSpeed: $('scroll-speed'),
  naturalScroll: $('natural-scroll'),
  haptics: $('haptics'),
  keepAwake: $('keep-awake'),
};

function renderSettings() {
  fields.sensitivity.value = settings.sensitivity;
  fields.scrollSpeed.value = settings.scrollSpeed;
  fields.naturalScroll.checked = settings.naturalScroll;
  fields.haptics.checked = settings.haptics;
  fields.keepAwake.checked = settings.keepAwake;
  $('sensitivity-out').textContent = `${settings.sensitivity.toFixed(1)}×`;
  $('scroll-out').textContent = `${settings.scrollSpeed.toFixed(1)}×`;
}

function readSettingsForm() {
  settings = saveSettings({
    sensitivity: Number(fields.sensitivity.value),
    scrollSpeed: Number(fields.scrollSpeed.value),
    naturalScroll: fields.naturalScroll.checked,
    haptics: fields.haptics.checked,
    keepAwake: fields.keepAwake.checked,
  });
  renderSettings();
  updateWakeLock();
}

for (const field of Object.values(fields)) {
  field.addEventListener('input', readSettingsForm);
  field.addEventListener('change', readSettingsForm);
}

$('settings-btn').addEventListener('click', () => {
  renderSettings();
  dialog.showModal();
});

$('forget-pc').addEventListener('click', () => {
  forgetToken();
  token = null;
  connection.stop();
  dialog.close();
  onStatus('unauthorized', { reason: 'forgotten' });
});

$('pair-retry').addEventListener('click', () => {
  token = readPairingToken();
  if (token) {
    pairScreen.hidden = true;
    connection.start();
  }
});

// --- Keep the screen on while the remote is open (needs HTTPS) -------------

async function updateWakeLock() {
  const wanted = settings.keepAwake && document.visibilityState === 'visible';
  if (!wanted) {
    await wakeLock?.release().catch(() => {});
    wakeLock = null;
    return;
  }
  if (wakeLock || !('wakeLock' in navigator)) return;
  try {
    wakeLock = await navigator.wakeLock.request('screen');
    wakeLock.addEventListener('release', () => {
      wakeLock = null;
    });
  } catch {
    wakeLock = null; // not allowed right now (battery saver, etc.)
  }
}

// --- App lifecycle ----------------------------------------------------------

document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') {
    connection.nudge(); // reconnect instantly when you come back
  } else {
    touchpad.reset(); // don't leave a drag half-finished
    releaseAllButtons();
    setDragLock(false);
  }
  updateWakeLock();
});
window.addEventListener('online', () => connection.nudge());

if (token) connection.start();
else onStatus('unauthorized', { reason: 'missing' });
updateWakeLock();
