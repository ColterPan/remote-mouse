# Security

A remote mouse is powerful: whoever controls it controls your PC. These are
the protections, and what they do and don't cover.

## Protections

| Layer | What it does | Code |
|---|---|---|
| **Local network only** | Requests from public internet addresses are refused before anything else, even if a router forwards the port by mistake. | `security.is_private_address`, `server.private_network_only` |
| **Pairing token** | A 128-bit random secret from the QR code must be the first message. It is compared in constant time. | `config.new_token`, `security.tokens_match` |
| **Lockout** | 5 wrong tokens (or login timeouts) from one address → blocked for 60 s. The lockout is checked again at the moment of each guess, so parallel connections can't bypass it. | `security.FailedAuthLimiter`, `server._authenticate` |
| **Connection limits** | At most 2 not-yet-logged-in connections per address (8 total) must log in within 5 s; at most 4 phones at once. | `server.py` |
| **DNS-rebinding protection** | The `Host` header must be a private IP, `localhost` or this PC's name, so a malicious website can't pose as the PC. | `security.is_trusted_host` |
| **New-device alert** | A Windows notification appears when a phone connects from a new address, so you'd notice an intruder. | `__main__.py` |
| **Encryption** | All traffic uses TLS 1.2+ with a certificate generated on your PC. Keystrokes can't be read by others on the Wi-Fi. | `tls.py` |
| **Strict input validation** | Every message is checked against a fixed schema: known types, keys and buttons only; numbers clamped; text length-limited and stripped of control characters; 4 KB message cap. | `protocol.py` |
| **Cross-site protection** | WebSocket `Origin` must be the PC itself. A Content-Security-Policy allows only the PC's own scripts, and there are no third-party scripts or CDNs. | `server.py` |
| **No stuck input** | Modifier keys are always released. Held mouse buttons are released when a phone disconnects. | `input_controller.py`, `server.py` |
| **Least privilege** | Runs as your normal user (no admin). Autostart uses the per-user registry key. | `autostart.py` |
| **Nothing phones home** | No telemetry, no ads, no accounts, no outbound network connections. | the whole codebase |
| **Supply chain** | Pinned dependencies, Dependabot, `pip-audit` and `bandit` in CI. The exe is built by GitHub Actions from public source, with SHA-256 checksums. | `.github/` |

## Your part

- When Windows Firewall asks, allow **Private networks** only, not Public.
- Keep the pairing link and QR code private: anyone with them, on your network, can control the PC.
- Lost a phone or shared the QR by accident? Use **tray icon → Reset pairing…**.
- On public Wi-Fi, quit Remote Mouse or make sure the network is set to *Public* in Windows (so the firewall blocks it).
- Verify downloads: compare `Get-FileHash RemoteMouse.exe` with `SHA256SUMS.txt` on the release page.

## Known limitations

- **Self-signed certificate:** Chrome warns once. Accept it only when you opened the link from your own PC's QR code. The Android app (phase 2) pins the certificate fingerprint instead.
- **Pairing on a hostile network:** if an attacker on the *same* Wi-Fi actively intercepts traffic (ARP/DHCP spoofing) at the exact moment you pair and accept the warning, they could capture the token. Pair on your own home network. If you get a "phone connected" alert you don't recognise, use **Reset pairing**. Planned: single-use pairing codes exchanged for per-device keys that can be revoked individually.
- **"Private" doesn't mean "trusted":** on café or hotel Wi-Fi, every customer has a private address. There the token is the only protection, so quit the app or keep the network set to *Public*.
- **One shared token:** all paired phones share the same token. Reset pairing revokes all of them at once.
- **Admin windows:** Windows blocks normal programs from controlling elevated windows (UAC prompts, Task Manager). This is a Windows security feature, and Remote Mouse deliberately doesn't run as admin.
- **Same-network trust:** the token protects against other devices on your Wi-Fi, but a device that already knows the token (e.g. a stolen phone) can connect until you reset pairing.

## Reporting a vulnerability

Please open a private security advisory on GitHub (**Security → Report a vulnerability**) rather than a public issue.
