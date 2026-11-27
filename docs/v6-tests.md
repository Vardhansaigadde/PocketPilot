# v6 test checklist: Android app

Start `python run.py` on the laptop (it shows the QR code with the certificate fingerprint).
Install the app (`android_app/`, or the APK from Releases) on the phone, same Wi-Fi.

| # | Do | Expected | ✓ |
|---|----|----------|:-:|
| 1 | Open the app, allow the camera, scan the QR code | The PocketPilot page opens, **no "not private" warning** | ☐ |
| 2 | Touchpad: move, tap, two-finger scroll, type | Works as in the browser | ☐ |
| 3 | Tap the mic, allow the microphone, say "scroll down" | Scrolls; reply shown and spoken | ☐ |
| 4 | Switch to **తె**, say "వాల్యూమ్ పెంచు" | Volume up; reply **spoken in Telugu** | ☐ |
| 5 | Approve card: "message amma that test" → **Cancel** | Card works; nothing sent | ☐ |
| 6 | Phone **back** button | Menu: Reload / Find the laptop again / Pair again / Close | ☐ |
| 7 | Close the app, open it again | Goes straight to the remote (pairing remembered) | ☐ |
| 8 | Laptop joins another Wi-Fi or hotspot (new address), restart `python run.py`, phone on the same network, open the app | "Looking for your laptop…", then the remote opens at the new address | ☐ |
| 9 | Stop `python run.py` | "Can't find the laptop…" with **Try again**; works again after restarting it | ☐ |
| 10 | Menu → Pair again → scan | Pairs again | ☐ |
| 11 | Scan a QR code from `python run.py --http` | Explains HTTPS is needed; doesn't connect | ☐ |
| 12 | Browser (not the app): open the QR link as before | Still works exactly like v5 (speech, vibration) | ☐ |
