# Remote Mouse protocol (version 1)

The phone and the PC talk over a WebSocket at `wss://<pc-address>:8765/ws`.
Every message is one JSON object with a type field `"t"`. The PC's validator
is [`pc/remote_mouse/protocol.py`](../pc/remote_mouse/protocol.py), and this
document must stay in sync with it.

## Connection lifecycle

1. The phone opens the WebSocket.
2. Its **first message must be `auth`**, sent within 5 seconds. A timeout counts as a failed attempt.
3. The PC answers `hello` (success) or `error` and then closes the socket.
4. From then on the phone sends input messages. It also sends `ping` every
   ~4 s, and the PC answers `pong`.

## Phone → PC

| `t` | Fields | Meaning | Limits |
|---|---|---|---|
| `auth` | `token` (string), `v` (int) | pair / log in | token ≤ 256 chars, `v` must be `1` |
| `ping` | — | keep-alive | |
| `move` | `dx`, `dy` (number) | move the pointer by pixels | clamped to ±1000 |
| `click` | `b` (button, default `left`), `n` (int, default 1) | click (`n=2` double-click) | `n` 1–3 |
| `down` / `up` | `b` | press / release a button (dragging) | |
| `scroll` | `dx`, `dy` (number, default 0) | wheel notches; `dy>0` up, `dx>0` right; fractions allowed | clamped to ±20 |
| `text` | `s` (string) | type text (Unicode, `\n` = Enter, `\t` = Tab) | ≤ 500 chars; control chars removed |
| `key` | `k` (key name), `mods` (list) | press a key or shortcut | see below |

**Buttons:** `left`, `right`, `middle`

**Modifiers (`mods`):** `ctrl`, `alt`, `shift`, `win`. They're always pressed in that order and released in reverse.

**Keys (`k`):**
- Letters `a`–`z` and digits `0`–`9`, for shortcuts like Ctrl+C
- `esc` `tab` `enter` `backspace` `delete` `insert` `space`
- `home` `end` `page_up` `page_down` `up` `down` `left` `right`
- `caps_lock` `print_screen` `menu` `win`
- `f1` … `f12`
- `volume_up` `volume_down` `volume_mute` `media_play_pause` `media_next` `media_previous`

Example: `{"t":"key","k":"esc","mods":["ctrl","shift"]}` opens Task Manager.

## PC → phone

| `t` | Fields | When |
|---|---|---|
| `hello` | `v`, `name` (PC name) | auth accepted |
| `pong` | — | reply to `ping` |
| `error` | `reason` | bad message (the session continues), or auth failure (the PC closes the socket after it) |

## WebSocket close codes

| Code | Meaning | What the phone does |
|---|---|---|
| 4401 | wrong or missing token / auth timeout | shows "scan the QR code again" |
| 4426 | protocol version mismatch | asks you to update |
| 4001 | pairing was reset on the PC | reconnects, then gets 4401 |

## HTTP errors on `/ws`

`403` means a non-private address, or a foreign `Origin` or `Host`. `429` means locked out after 5 wrong tokens (wait 60 s). `503` means too many phones are connected (max 4), or too many connections are waiting to log in (2 per address, 8 total).

## Limits

A message can be at most 4096 bytes.

## Adding a message type

1. Add a dataclass and a `_parse_<name>` function in `protocol.py`, then register it in `_PARSERS`.
2. Handle it in `input_controller.execute()`, and add a method to `InputController`, `PynputController` and `FakeController`.
3. Send it from the phone, e.g. `send({ t: 'name', ... })` in `web/js/`.
4. Add tests in `pc/tests/` and document the message here.
