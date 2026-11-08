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
| **Supply chain** | Pinned dependencies, Dependabot, `pip-audit`, `bandit` and `gitleaks` (secret scan over the full history) in CI. The Gradle wrapper is validated. Releases are built by GitHub Actions from public source, with SHA-256 checksums. | `.github/` |

## Android app

| Protection | What it does | Code |
|---|---|---|
| **Certificate pinning** | The app trusts **only** the certificate whose SHA-256 fingerprint came from your PC's QR code. There's no "trust all" fallback. The token is sent only after that check passes, so a spoofed PC, or a fake network announcement, never receives it. | `FingerprintTrustManager.kt`, `PinnedSocket.kt` |
| **Token never reaches the web page** | Pairing tokens stay in native storage. The page only sees PC names and addresses. | `PcStore.kt` (`toPublicJson`), `NativeBridge.kt` |
| **No backups of pairing data** | `allowBackup=false`, and data-extraction rules exclude everything from cloud backup and device transfer. | `AndroidManifest.xml`, `res/xml/` |
| **Locked-down WebView** | The bundled UI is served from the app itself, with no file or content access and no navigation away. The bridge accepts messages only from the bundled page's origin, and WebView debugging is on in debug builds only. | `MainActivity.kt` |
| **No plain HTTP** | `cleartextTrafficPermitted="false"`. | `network_security_config.xml` |
| **Strict QR parsing, local network only** | Only well-formed `https://host:port/#t=…&fp=…` links pointing at a **private/link-local IPv4 address** are accepted. A malicious QR code can't pair the app with an internet server. | `PairingLink.kt` |
| **Verified addresses only** | When the PC is found at a new address, that address is saved only **after** the PC proves its identity (pinned TLS + accepted token), so a fake network announcement can't redirect the app. | `RemoteSession.kt` |
| **Signing key never in the repo** | Release APKs are signed in GitHub Actions from encrypted secrets. The key is written to a temporary file and deleted after the build. | `.github/workflows/release.yml` |
| **Test hooks only in debug builds** | The adb test extras (`rm_pair_link`, `rm_set_host`) are compiled in but ignored unless `BuildConfig.DEBUG`. | `MainActivity.kt` |

The mDNS announcement contains only the protocol version and the certificate fingerprint. It doesn't include your PC's name (the service is called "Remote Mouse <8 hex characters>"), and it never contains the token. To turn discovery off, set `"discovery": false` in `%APPDATA%\RemoteMouse\config.json`. The app then reconnects only to the address it knows.

**CI/CD hardening:**
- Every third-party GitHub Action is pinned to an exact commit SHA.
- Tag names reach scripts only through environment variables, never pasted into them.
- Debug APKs (which contain test hooks) are never published.
- The uninstaller offers to delete the pairing data in `%APPDATA%\RemoteMouse`.

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
