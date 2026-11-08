/**
 * settings.js — Remembers your preferences and pairing code on this phone.
 *
 * Stored in the browser's localStorage, which belongs only to this exact
 * address (https://<pc-ip>:<port>) — other websites can't read it.
 *
 * Everything is validated on load: if storage is corrupted, blocked (private
 * mode) or holds out-of-range values, we quietly fall back to defaults.
 * Functions return NEW objects rather than modifying the old ones.
 */

const SETTINGS_KEY = 'remote-mouse.settings.v1';
const TOKEN_KEY = 'remote-mouse.token.v1';

export const DEFAULT_SETTINGS = Object.freeze({
  sensitivity: 1.6,
  scrollSpeed: 1.0,
  naturalScroll: true,
  haptics: true,
  keepAwake: true,
});

const RANGES = {
  sensitivity: [0.5, 4],
  scrollSpeed: [0.3, 3],
};

/** Return a clean settings object: known keys only, right types, in range. */
export function sanitizeSettings(raw) {
  const source = raw && typeof raw === 'object' ? raw : {};
  const result = { ...DEFAULT_SETTINGS };
  for (const [key, fallback] of Object.entries(DEFAULT_SETTINGS)) {
    const value = source[key];
    if (typeof fallback === 'boolean' && typeof value === 'boolean') {
      result[key] = value;
    } else if (typeof fallback === 'number' && Number.isFinite(value)) {
      const [lo, hi] = RANGES[key];
      result[key] = Math.min(hi, Math.max(lo, value));
    }
  }
  return Object.freeze(result);
}

function safeGet(key) {
  try {
    return globalThis.localStorage?.getItem(key) ?? null;
  } catch {
    return null; // storage disabled
  }
}

function safeSet(key, value) {
  try {
    if (value === null) globalThis.localStorage?.removeItem(key);
    else globalThis.localStorage?.setItem(key, value);
  } catch {
    // storage disabled or full — settings just won't persist
  }
}

export function loadSettings() {
  try {
    return sanitizeSettings(JSON.parse(safeGet(SETTINGS_KEY) ?? '{}'));
  } catch {
    return sanitizeSettings({});
  }
}

export function saveSettings(settings) {
  const clean = sanitizeSettings(settings);
  safeSet(SETTINGS_KEY, JSON.stringify(clean));
  return clean;
}

export const loadToken = () => safeGet(TOKEN_KEY);
export const saveToken = (token) => safeSet(TOKEN_KEY, token);
export const forgetToken = () => safeSet(TOKEN_KEY, null);

/**
 * Read the pairing token from a URL fragment like "#t=abc&fp=123".
 * Returns null if absent or obviously malformed.
 */
export function tokenFromHash(hash) {
  const params = new URLSearchParams(String(hash || '').replace(/^#/, ''));
  const token = params.get('t');
  return token && /^[A-Za-z0-9_-]{22,128}$/.test(token) ? token : null;
}
