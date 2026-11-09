/**
 * app.js — Starts the phone remote and wires all the pieces together.
 *
 *   settings.js   preferences (+ pairing token in browser mode)
 *   connection.js the link to the PC (auto-reconnect, dead-link detection)
 *   native.js     Android-app mode: the native side owns the connection
 *   touchpad.js   touchpad + scroll strip (+ momentum scrolling)
 *   keyboard.js   typing, special keys, shortcuts, media keys
 *   viewport.js   keeps the layout right while the phone keyboard is open
 *
 * Two modes, one page:
 *  • Browser: the QR code opens https://<pc>:8765/#t=<token>. We save the token,
 *    remove it from the address bar, and reconnect with it from then on.
 *  • Android app: the app stores your paired PCs natively (tokens never reach
 *    this page). On launch we auto-connect to the last PC; if its IP changed,
 *    the app finds it again on the network. Pairing = "Scan QR code" in-app.
 */

import { Connection } from './connection.js';
import { createKeyboard } from './keyboard.js';
import { NativeHost, nativeBridge } from './native.js';
import {
  SPEED_PRESETS,
  forgetToken,
  loadSettings,
  loadToken,
  saveSettings,
  saveToken,
  tokenFromHash,
} from './settings.js';
import { createTouchpad } from './touchpad.js';
import { trackViewport } from './viewport.js';

const APP_VERSION = '1.1.1';
const $ = (id) => document.getElementById(id);

const bridge = nativeBridge();
const native = bridge ? new NativeHost(bridge) : null;
const isApp = native !== null;

let settings = loadSettings();
let token = isApp ? null : readPairingToken();
let pcs = [];
let currentPcId = null;
let pcName = '';
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

// --- Status chip + banner ---------------------------------------------------

const statusEl = $('status');
const statusText = $('status-text');
const banner = $('banner');
const bannerText = $('banner-text');
const bannerRetry = $('banner-retry');
const pairScreen = $('pair-screen');

function showBanner(kind, text, withRetry) {
  banner.dataset.kind = kind;
  bannerText.textContent = text;
  bannerRetry.hidden = !withRetry;
  banner.hidden = false;
}

function onStatus(state, detail = {}) {
  statusEl.dataset.state = state;
  // The PC releases held buttons when a phone disconnects, so the lock is off.
  if (state !== 'connected') showDragLock(false);
  const name = detail.name || pcName || 'your PC';

  switch (state) {
    case 'connected':
      if (detail.name) pcName = detail.name;
      statusText.textContent = pcName || 'Connected';
      banner.hidden = true;
      pairScreen.hidden = true;
      break;
    case 'connecting':
      statusText.textContent = 'Connecting…';
      break;
    case 'searching':
      statusText.textContent = 'Searching…';
      showBanner('searching', `Looking for ${name} on your Wi-Fi…`, false);
      break;
    case 'unauthorized':
      statusText.textContent = 'Not paired';
      banner.hidden = true;
      showPairScreen(detail.reason);
      break;
    default: // offline
      statusText.textContent = 'Offline';
      if (detail.reason === 'version') {
        showBanner('error', 'Update Remote Mouse on your PC and phone.', false);
      } else {
        const seconds = Math.max(1, Math.round((detail.retryInMs || 0) / 1000));
        showBanner('error', `Can't reach ${name}. Retrying in ${seconds}s…`, true);
      }
  }
}

// --- Connection ---------------------------------------------------------------

const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
const connection = new Connection({
  url: `${scheme}://${location.host}/ws`,
  getToken: () => (isApp ? currentPcId && 'native' : token),
  onStatus,
  createSocket: isApp ? () => native.openSocket(currentPcId) : undefined,
  // App: connect (4 s) + network search (5 s) + reconnect (4 s) must fit.
  connectTimeoutMs: isApp ? 20000 : undefined,
});
bannerRetry.addEventListener('click', () => connection.nudge());

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

// --- Touchpad, tips & keyboard ----------------------------------------------

const tips = $('tips');
function dismissTips() {
  if (tips.hidden) return;
  tips.hidden = true;
  settings = saveSettings({ ...settings, tipsSeen: true });
}
tips.hidden = settings.tipsSeen;
$('tips-ok').addEventListener('click', dismissTips);

const touchpad = createTouchpad({
  element: $('touchpad'),
  strip: $('scroll-strip'),
  send,
  getOptions: () => ({
    sensitivity: settings.sensitivity,
    scrollSpeed: settings.scrollSpeed,
    naturalScroll: settings.naturalScroll,
    momentum: settings.momentum,
  }),
  onClick: haptic,
  onFirstUse: dismissTips,
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

// --- Phone keyboard open/close: keep the touchpad usable (see viewport.js) ---

trackViewport($('app'), (keyboardOpen) => {
  $('app').classList.toggle('kb-open', keyboardOpen);
  touchpad.reset(); // the pad just changed size; don't continue a half gesture
  // Keyboard hidden by Android's back button / the keyboard's own hide key:
  // close the keyboard panel too, so the toolbar shows the real state.
  if (!keyboardOpen && openPanel === 'panel-keyboard') showPanel(null);
});

// --- Pairing / "Your PCs" screen ---------------------------------------------

const PAIR_REASONS = {
  missing: isApp
    ? 'Pair once and the app connects automatically from then on.'
    : "This phone isn't paired yet.",
  rejected: 'Your PC no longer accepts this phone (pairing was reset). Scan the new QR code.',
  forgotten: 'This phone forgot the PC. Scan the QR code to pair again.',
  switch: 'Choose a PC, or add another one.',
  badQr: "That doesn't look like a Remote Mouse QR code. Try again.",
};

function renderPcList() {
  const list = $('pc-list');
  list.replaceChildren(
    ...pcs.map((pc) => {
      const item = document.createElement('li');
      item.className = `pc-item${pc.id === currentPcId ? ' current' : ''}`;

      const main = document.createElement('button');
      main.type = 'button';
      main.className = 'pc-main';
      const icon = document.createElement('span');
      icon.className = 'pc-icon';
      icon.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h16v10H4V5Zm-2 12h20v2H2v-2Z"/></svg>';
      const text = document.createElement('span');
      text.className = 'pc-text';
      const name = document.createElement('span');
      name.className = 'pc-name';
      name.textContent = pc.name; // textContent: names are never treated as HTML
      const hostLine = document.createElement('span');
      hostLine.className = 'pc-host';
      hostLine.textContent = pc.host;
      text.append(name, hostLine);
      main.append(icon, text);
      main.addEventListener('click', () => selectPc(pc.id));

      const forget = document.createElement('button');
      forget.type = 'button';
      forget.className = 'pc-forget';
      forget.setAttribute('aria-label', `Forget ${pc.name}`);
      forget.textContent = '✕';
      forget.addEventListener('click', () => forgetPc(pc.id));

      item.append(main, forget);
      return item;
    }),
  );
  $('pc-list-wrap').hidden = pcs.length === 0;
}

function showPairScreen(reason = 'missing') {
  $('pair-reason').textContent = PAIR_REASONS[reason] || PAIR_REASONS.missing;
  if (isApp) {
    $('pair-title').textContent = pcs.length ? 'Your PCs' : 'Add your PC';
    $('step-scan').textContent = 'Tap “Scan QR code” below and point the camera at it.';
    $('pair-scan').hidden = false;
    $('pair-retry').hidden = true;
    $('pair-steps').hidden = pcs.length > 0 && reason === 'switch';
    renderPcList();
  }
  pairScreen.hidden = false;
}

function selectPc(id) {
  const pc = pcs.find((p) => p.id === id);
  if (!pc) return;
  currentPcId = id;
  pcName = pc.name;
  pairScreen.hidden = true;
  connection.stop();
  connection.start();
}

function forgetPc(id) {
  const pc = pcs.find((p) => p.id === id);
  // eslint-disable-next-line no-alert
  if (!pc || !confirm(`Forget ${pc.name}? You'll need to scan its QR code again.`)) return;
  const wasCurrent = id === currentPcId;
  if (wasCurrent) {
    connection.stop();
    currentPcId = null;
  }
  native.request('forget', { id });
  // Don't leave a dead touchpad on screen: go to the PC list.
  if (wasCurrent) {
    statusEl.dataset.state = 'unauthorized';
    statusText.textContent = 'Not connected';
    showPairScreen('switch');
  }
}

$('pair-scan').addEventListener('click', () => native?.request('scan'));
$('pair-retry').addEventListener('click', () => {
  token = readPairingToken();
  if (token) {
    pairScreen.hidden = true;
    connection.start();
  }
});

// --- Settings sheet -----------------------------------------------------------

const dialog = $('settings');
const fields = {
  sensitivity: $('sensitivity'),
  scrollSpeed: $('scroll-speed'),
  naturalScroll: $('natural-scroll'),
  momentum: $('momentum'),
  haptics: $('haptics'),
  keepAwake: $('keep-awake'),
};
const presetButtons = Array.from(document.querySelectorAll('[data-preset]'));

function renderSettings() {
  fields.sensitivity.value = settings.sensitivity;
  fields.scrollSpeed.value = settings.scrollSpeed;
  fields.naturalScroll.checked = settings.naturalScroll;
  fields.momentum.checked = settings.momentum;
  fields.haptics.checked = settings.haptics;
  fields.keepAwake.checked = settings.keepAwake;
  $('sensitivity-out').textContent = `${settings.sensitivity.toFixed(1)}×`;
  $('scroll-out').textContent = `${settings.scrollSpeed.toFixed(1)}×`;
  for (const button of presetButtons) {
    button.classList.toggle('active', SPEED_PRESETS[button.dataset.preset] === settings.sensitivity);
  }
}

function applySettings(next) {
  settings = saveSettings(next);
  renderSettings();
  updateWakeLock();
}

function readSettingsForm() {
  applySettings({
    ...settings,
    sensitivity: Number(fields.sensitivity.value),
    scrollSpeed: Number(fields.scrollSpeed.value),
    naturalScroll: fields.naturalScroll.checked,
    momentum: fields.momentum.checked,
    haptics: fields.haptics.checked,
    keepAwake: fields.keepAwake.checked,
  });
}

for (const field of Object.values(fields)) {
  field.addEventListener('input', readSettingsForm);
  field.addEventListener('change', readSettingsForm);
}
for (const button of presetButtons) {
  button.addEventListener('click', () => {
    applySettings({ ...settings, sensitivity: SPEED_PRESETS[button.dataset.preset] });
    haptic();
  });
}

$('settings-btn').addEventListener('click', () => {
  renderSettings();
  dialog.showModal();
});
statusEl.addEventListener('click', () => {
  if (isApp) showPairScreen('switch');
  else connection.nudge();
});

$('switch-pc').hidden = !isApp;
$('switch-pc').addEventListener('click', () => {
  dialog.close();
  showPairScreen('switch');
});

$('forget-pc').addEventListener('click', () => {
  dialog.close();
  if (isApp) {
    if (currentPcId) forgetPc(currentPcId);
    return;
  }
  forgetToken();
  token = null;
  connection.stop();
  onStatus('unauthorized', { reason: 'forgotten' });
});

$('version').textContent = `Remote Mouse ${APP_VERSION} · ${isApp ? 'Android app' : 'web remote'}`;

// --- Keep the screen on while the remote is open ----------------------------

async function updateWakeLock() {
  const wanted = settings.keepAwake && document.visibilityState === 'visible';
  if (isApp) {
    native.request('keepAwake', { on: settings.keepAwake });
    return;
  }
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

if (isApp) {
  let firstList = true;
  native.on('pcs', (event) => {
    pcs = Array.isArray(event.pcs) ? event.pcs : [];
    const current = pcs.find((p) => p.id === currentPcId);
    if (current) pcName = current.name;
    renderPcList();
    if (firstList) {
      firstList = false;
      if (event.lastId) selectPc(event.lastId); // auto-connect, no QR needed
      else showPairScreen('missing');
    } else if (!pcs.length) {
      showPairScreen('missing');
    }
  });
  native.on('paired', (event) => selectPc(event.id));
  native.on('scanError', () => showPairScreen('badQr'));
  native.on('status', (event) => onStatus(event.state, { name: event.name }));
  native.request('init');
} else if (token) {
  connection.start();
} else {
  onStatus('unauthorized', { reason: 'missing' });
}
updateWakeLock();
