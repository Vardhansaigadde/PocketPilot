# PocketPilot for Android

The phone remote for your laptop as an installable app. It shows the same phone page a
browser shows (touchpad, voice, Approve cards, Telugu) and adds what a browser can't do:

- **Trusts only your laptop:** pairing pins the laptop's own certificate authority (its SHA-256 is in
  the QR code), so there is no "not private" warning, and any other certificate is refused.
- **Finds the laptop again** when its Wi-Fi address changes (UDP discovery on port 8766; the pairing
  token never goes over the air).
- **Speaks replies with the phone's voice**, including Telugu, and vibrates on taps.

| File | What it does |
| --- | --- |
| `lib/main.dart` | Opens the remote if paired, otherwise the QR scanner |
| `lib/pair_screen.dart` | Scans the QR code, downloads and checks the laptop's CA certificate |
| `lib/remote_screen.dart` | The laptop's page in a web view: certificate check, mic, speech/vibration bridge, reconnect, back-button menu |
| `lib/pairing.dart` | Reads the QR link; saves the pairing in Android's encrypted storage |
| `lib/discovery.dart` | Finds the laptop on the Wi-Fi |
| `lib/trust.dart` | CA download + fingerprint check; asks Android to verify the laptop's certificate |
| `android/.../MainActivity.kt` | The certificate check itself (`java.security`) |

Build and test (Flutter SDK + Android SDK):

```powershell
flutter test
flutter build apk --release
```
