# PocketPilot

**Your phone becomes a touchpad, keyboard and voice remote for your laptop, with a free local AI agent that does tasks on screen when you ask in English or Telugu.**

Zero cost: everything is open source and runs on your own laptop. No cloud account needed.

> Status: **v1 (touchpad) works. v2 (voice commands) is built and being tested** against the [25-command checklist](docs/v2-commands.md). The AI agent and Telugu are next. See the [roadmap](#roadmap).

<!-- Add a demo GIF here once recorded: docs/demo-v1.gif -->

## Voice commands (v2)

Hold **🎤** on the phone and speak, type in the command box, or say **"Hey Jarvis"** to the laptop and then your command. The reply shows on the phone and is spoken out loud.

| Say | What happens |
| --- | --- |
| "scroll down", "scroll up a lot", "click", "right click", "double click" | Mouse |
| "type hello world", "press enter", "copy", "paste", "undo", "select all" | Keyboard |
| "volume up", "mute", "pause", "next song" | Media keys |
| "switch app", "show desktop" | Windows shortcuts |
| "open Chrome / Edge / Notepad / Calculator / File Explorer / Settings / WhatsApp / Spotify / VS Code / Paint / Word / Excel / PowerPoint / Camera" | Opens that app |
| "close the window" | Asks **Approve** on the phone first |
| "show grid" → "click 14" | Numbered grid over the screen; clicks the middle of box 14 |
| "weather", "weather in Hyderabad", "when is sunset" | Open-Meteo forecast |
| "air quality in Delhi" | AQI + simple advice |
| "who is APJ Abdul Kalam", "tell me about the Taj Mahal" | Short Wikipedia summary |
| "search YouTube for lofi", "search Amazon for a wireless mouse" | Opens Edge on the search results |
| "stop" (or the **■** button) | Cancels everything |

Common phrases are matched instantly without AI (about 0.5 s from the phone mic). Anything else ("I want to listen to some lofi") goes to a small AI model running on your laptop through Ollama, which can only answer with one of the actions above.

### Voice setup (one time)
1. Install **Ollama** (free) from [ollama.com](https://ollama.com), then in PowerShell: `ollama pull qwen3:4b` (about 2.5 GB). Without it, the fixed phrases above still work.
2. `python -m pip install -r requirements.txt`. The first start downloads the Whisper speech model (about 145 MB) and the wake-word model (about 5 MB).
3. Optional: copy `.env.example` to `.env` and set your home city (for "weather" with no city) and your GitHub repo URL (Wikipedia asks apps for a contact link).

Use `python run.py --no-wake` to turn off the laptop mic, or `--no-voice` for touchpad only.

## Touchpad (v1)

| On your phone | On your laptop |
| --- | --- |
| 1 finger move | Moves the cursor (slow = precise, fast flick = far) |
| Tap | Left click |
| Double tap | Double-click |
| Tap, then touch again and move | Click-and-drag (like a laptop touchpad) |
| Hold still, then drag | Click-and-drag (select text, move files) |
| 2-finger tap | Right click |
| 2-finger slide | Scroll (natural or classic, your choice) |
| Pinch | Zoom (Ctrl + wheel) |
| 3-finger tap | Middle click |
| 3-finger swipe left / right | Switch apps |
| 3-finger swipe up / down | All windows / show desktop |
| Shortcut buttons | Switch app, Desktop, All windows, Copy, Paste in one tap |
| ⌨ Type | Your phone keyboard types on the laptop |
| Bottom buttons | Esc, Tab, Enter, Backspace, arrows, copy/paste, volume, play/pause |

The top bar shows the round-trip time to the laptop, so you can see the lag.

## Quick start (Windows)

You need **Python 3.11+** ([python.org](https://www.python.org/downloads/), tick "Add python.exe to PATH") and your phone on the **same Wi-Fi** as the laptop.

```powershell
cd pocketpilot
python -m pip install -r requirements.txt
python run.py
```

1. A QR code appears (in the terminal and as an image).
2. Scan it with your phone camera and open the link.
3. The first time, the phone says the connection **isn't private**. That's expected: PocketPilot makes its own certificate on your laptop. Tap **Advanced → Proceed**.
4. If Windows asks about the firewall, allow **Private networks** only.
5. Optional: in your phone browser menu, choose **Add to Home screen** so it opens like an app.

Or just double-click `start.bat` after installing the requirements.

To unpair every phone and make a new QR code: `python run.py --new-token`

### Optional: remove the "not private" warning (recommended)
PocketPilot runs over **HTTPS**, because phones only allow the microphone (voice commands) on secure pages. It makes its own certificates in `data/`, for free.

To make your phone trust them for good (Android):
1. On the phone, open `https://<laptop-ip>:8765/pocketpilot-ca.crt` (the exact link is printed in the terminal) and download it.
2. Go to **Settings → Security → More security settings → Install from device storage → CA certificate** (wording varies by phone), and pick the downloaded file.
3. Reopen PocketPilot: no warning, and Add to Home screen works like a real app.

This certificate can **only** vouch for home-network addresses (192.168.x.x, 10.x.x.x, 172.16–31.x.x) and `localhost`, so it can't be used to fake real websites. If you change Wi-Fi, PocketPilot makes a new server certificate automatically and the phone keeps trusting it. You can remove it any time in the same Settings screen.

If you don't want HTTPS: `python run.py --http` (the touchpad works, voice won't).

### If the phone can't connect
- Phone and laptop must be on the same Wi-Fi. College and public Wi-Fi often block devices from talking to each other: use your **phone's hotspot** and connect the laptop to it.
- Make sure the Windows Firewall prompt was allowed for Private networks. If you dismissed it, open *Windows Security → Firewall → Allow an app* and tick Python for Private.
- Check the network is set to *Private* in Windows Wi-Fi settings, not *Public*.
- After updating from an older version, the address changed from `http://` to `https://`: scan the QR code once more.

## How it works

```
Phone (web app)  ──secure WebSocket (wss), same Wi-Fi, pairing token──►  Laptop server (FastAPI)
                                                              │ validate message (allow-list)
                                                              ▼
                                                           Input control (pynput) ──► Windows

Voice: phone mic / text box / "Hey Jarvis" ─► Whisper (speech → text, on the laptop)
       ─► fast-path phrases, else Ollama (local AI, answers only in the command format)
       ─► command checked against the allow-list ─► mouse, keys, apps, skills, grid
       ─► risky ones wait for Approve on the phone
```

- **web/**: the phone app (plain HTML + JavaScript). Touches are batched to at most one message per screen frame to keep lag low.
- **server/protocol.py**: every message must match a fixed schema (Pydantic). Unknown actions, huge movements and risky shortcuts are rejected before anything moves.
- **server/pairing.py**: a random token in the QR code; connections without it are refused.
- **server/certs.py**: makes a small local certificate authority and an HTTPS certificate for the laptop's Wi-Fi address, so the phone can use its mic.
- **server/input_control.py**: turns messages into real mouse and keyboard actions. Released safely if the phone disconnects mid-drag.
- **agent/**: the voice assistant. `commands.py` (every allowed action), `router.py` (instant phrases), `llm.py` (Ollama), `stt.py` (Whisper), `executor.py` (does the action), `approvals.py`, `grid.py`, `laptop_voice.py` (wake word), `apps.py` (the only apps it can open).
- **skills/**: weather, air quality, Wikipedia and web search. Free, no API keys.

## Safety

- Only devices with the pairing token can connect; the server is meant for your home Wi-Fi only.
- Everything between phone and laptop is encrypted (HTTPS / secure WebSocket), so others on the Wi-Fi can't read your typing or steal the pairing token. Private keys stay in `data/` and are never sent to the phone.
- The phone can only trigger actions on a fixed allow-list. It cannot run programs or commands.
- The AI model never runs anything itself: its answer must match the command format exactly, or nothing happens. It can only open apps from a fixed list (no terminal, no PowerShell), and searches only open a results page.
- Closing a window waits for **Approve** on the phone and cancels itself after 30 seconds.
- Voice audio is processed on the laptop and never saved. Weather, air quality and Wikipedia are the only things that go to the internet, and they only send the place or topic.
- Kill switch: the **■** button, saying "stop", or **Ctrl+C** in the terminal.

## Development

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest
```

Tests use a fake controller, fake internet and a fake AI model, so they never move your real mouse, open apps or need Ollama.

## Roadmap

| Version | Adds |
| --- | --- |
| **v1 Touchpad** ✅ | Phone touchpad, keyboard, media keys, QR pairing |
| v2 Voice commands 🧪 | Phone mic + "Hey Jarvis" on the laptop ("Hey Pilot" later); open apps, weather, Edge/YouTube search, grid clicking |
| v3 Smart click + screen explainer | "Click the Login button", "summarize this page" |
| v4 Task agent | Multi-step tasks, WhatsApp replies with Approve, memory of what you did |
| v5 Telugu + parent mode | Telugu voice commands and replies, simple screen for parents, Android app |
| v6 Macros + MCP | "Watch me once" skills, MCP server for other AI apps |

## License

MIT
