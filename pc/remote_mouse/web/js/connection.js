/**
 * connection.js — Keeps a live, authenticated WebSocket to the PC.
 *
 * Responsibilities:
 *   • connect to wss://<this page's host>/ws and send the pairing token first
 *   • report status changes: 'connecting' → 'connected' / 'offline' /
 *     'unauthorized' (token rejected — the user must re-scan the QR code)
 *   • reconnect automatically with growing pauses (0.5 s, 1 s, 2 s … 5 s) so
 *     a sleeping PC or flaky Wi-Fi recovers without you doing anything
 *   • send a small "ping" every few seconds; if the PC stops answering we
 *     assume the link is dead and reconnect (phones often keep zombie sockets
 *     after switching networks)
 */

export const PROTOCOL_VERSION = 1;
const PING_INTERVAL_MS = 4000;
const PONG_TIMEOUT_MS = 9000;     // no message for this long → link is dead
const QUICK_CHECK_MS = 3000;      // after waking up, the PC must answer this fast
const CONNECT_TIMEOUT_MS = 6000;  // give up on a connection attempt after this
const BACKOFF_STEPS_MS = [500, 1000, 2000, 4000, 5000];

// Close codes defined by the PC (see server.py).
const CLOSE_UNAUTHORIZED = 4401;
const CLOSE_VERSION_MISMATCH = 4426;

/** Delay before reconnect attempt number `attempt` (0-based). */
export function backoffDelay(attempt) {
  return BACKOFF_STEPS_MS[Math.min(attempt, BACKOFF_STEPS_MS.length - 1)];
}

export class Connection {
  /**
   * @param {object} opts
   * @param {string} opts.url      e.g. "wss://192.168.1.5:8765/ws"
   * @param {() => string|null} opts.getToken
   * @param {(state: string, detail?: object) => void} opts.onStatus
   */
  constructor({ url, getToken, onStatus }) {
    this.url = url;
    this.getToken = getToken;
    this.onStatus = onStatus;
    this.ws = null;
    this.ready = false;
    this.attempt = 0;
    this.stopped = false;
    this.reconnectTimer = null;
    this.connectTimer = null;
    this.pingTimer = null;
    this.deadline = 0; // the PC must say something before this time
    this.lastTick = 0;
  }

  start() {
    this.stopped = false;
    this._open();
  }

  /** Reconnect right now (e.g. the phone screen just turned back on). */
  nudge() {
    if (this.stopped) return;
    if (this.ready && this.ws?.readyState === WebSocket.OPEN) {
      // Looks connected, but after sleep/network changes it may be a zombie.
      // Ask the PC to prove it's alive quickly.
      this._expectReplyWithin(QUICK_CHECK_MS);
      this.send({ t: 'ping' });
      return;
    }
    clearTimeout(this.reconnectTimer);
    this.attempt = 0;
    this._open();
  }

  stop() {
    this.stopped = true;
    clearTimeout(this.reconnectTimer);
    this._teardown();
  }

  /** Send a message if connected. Returns false if it was dropped. */
  send(message) {
    if (!this.ready || this.ws?.readyState !== WebSocket.OPEN) return false;
    this.ws.send(JSON.stringify(message));
    return true;
  }

  _open() {
    this._teardown();
    const token = this.getToken();
    if (!token) {
      this.onStatus('unauthorized', { reason: 'missing' });
      return;
    }
    this.onStatus('connecting');
    let ws;
    try {
      ws = new WebSocket(this.url);
    } catch {
      this._scheduleReconnect();
      return;
    }
    this.ws = ws;

    // If the PC is asleep or a firewall silently drops us, the socket can sit
    // in "connecting" for minutes. Don't wait — retry on our own schedule.
    this.connectTimer = setTimeout(() => {
      if (this.ws === ws && !this.ready) this._reconnectNow();
    }, CONNECT_TIMEOUT_MS);

    ws.addEventListener('open', () => {
      ws.send(JSON.stringify({ t: 'auth', token, v: PROTOCOL_VERSION }));
    });

    ws.addEventListener('message', (event) => {
      if (this.ws !== ws) return;
      this._expectReplyWithin(PONG_TIMEOUT_MS);
      let data;
      try {
        data = JSON.parse(event.data);
      } catch {
        return;
      }
      if (data.t === 'hello') {
        clearTimeout(this.connectTimer);
        this.ready = true;
        this.attempt = 0;
        this._startPinging();
        this.onStatus('connected', { name: typeof data.name === 'string' ? data.name : '' });
      }
    });

    ws.addEventListener('close', (event) => {
      if (this.ws !== ws) return; // an old socket we already replaced
      this._teardown();
      if (event.code === CLOSE_UNAUTHORIZED) {
        this.stopped = true;
        this.onStatus('unauthorized', { reason: 'rejected' });
      } else if (event.code === CLOSE_VERSION_MISMATCH) {
        this.stopped = true;
        this.onStatus('offline', { reason: 'version' });
      } else {
        this._scheduleReconnect();
      }
    });
    // 'error' is always followed by 'close', which handles reconnecting.
  }

  _expectReplyWithin(ms) {
    this.deadline = Date.now() + ms;
  }

  _startPinging() {
    clearInterval(this.pingTimer);
    this._expectReplyWithin(PONG_TIMEOUT_MS);
    this.lastTick = Date.now();
    this.pingTimer = setInterval(() => {
      const now = Date.now();
      const wasFrozen = now - this.lastTick > PING_INTERVAL_MS * 2;
      this.lastTick = now;
      if (wasFrozen) {
        // Android paused this page (screen off / app switch). The deadline is
        // stale, so don't judge the link yet — give it a fresh quick check.
        this._expectReplyWithin(QUICK_CHECK_MS);
      } else if (now > this.deadline) {
        // Dead link. Don't wait for the browser's slow close handshake
        // (can take ~60 s on a half-open connection): reconnect right away.
        this._reconnectNow();
        return;
      }
      this.send({ t: 'ping' });
    }, PING_INTERVAL_MS);
  }

  _reconnectNow() {
    this._teardown();
    this._scheduleReconnect();
  }

  _scheduleReconnect() {
    if (this.stopped) return;
    this.onStatus('offline');
    const delay = backoffDelay(this.attempt);
    this.attempt += 1;
    clearTimeout(this.reconnectTimer);
    this.reconnectTimer = setTimeout(() => this._open(), delay);
  }

  _teardown() {
    clearInterval(this.pingTimer);
    clearTimeout(this.connectTimer);
    this.ready = false;
    const ws = this.ws;
    this.ws = null;
    if (ws && ws.readyState <= WebSocket.OPEN) {
      try {
        ws.close();
      } catch {
        // already closing
      }
    }
  }
}
