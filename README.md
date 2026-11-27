# PocketPilot

**Your phone becomes a touchpad, keyboard and voice remote for your Windows laptop, with a local AI agent that does tasks on screen when you ask in English or Telugu.**

Zero cost: everything is open source and runs on your own laptop, on the CPU. No cloud account, no paid API.

<!-- Demo GIF goes here once recorded: ![PocketPilot demo](docs/demo.gif) -->

## What it can do

- **Touchpad and keyboard:** move, click, drag, scroll and type on the laptop from your phone's browser. Pair by scanning a QR code.
- **Voice commands:** "open notepad and type my shopping list", "search YouTube for lofi", "weather in Hyderabad", "close this tab". Common phrases run instantly; anything else goes to a small AI model on the laptop.
- **Clicks what you name:** "click the Sign in button", "play the second video", "open the first result". It reads the buttons on screen instead of guessing coordinates.
- **WhatsApp, safely:** "message Amma that I'll be late", "call Amma". It types the message, then waits: **nothing is sent or called until you tap Approve** on the phone.
- **Telugu:** speak Telugu or Telugu mixed with English ("ammaki call cheyyi", "హైదరాబాద్‌లో వాతావరణం ఎలా ఉంది") and get the answer in Telugu.
- **Reads the screen:** "summarize this page", "explain this error", "what's on my screen?".
- **Android app (optional):** the same remote as an installable app, with no certificate warning, and it finds the laptop again when its Wi-Fi address changes ([details](#android-app)).

**54 of 57 real tasks succeed (95%)** on a CPU-only laptop, across English, WhatsApp, Telugu and on-screen tasks ([how it was measured](#how-well-it-works)).

## Quick start (Windows)

You need:
- **Python 3.11+** ([python.org](https://www.python.org/downloads/); tick "Add python.exe to PATH")
- **Ollama** ([ollama.com](https://ollama.com), free) for the local AI. Without it the touchpad and the instant voice phrases still work.
- Your phone on the **same Wi-Fi** as the laptop

```powershell
cd pocketpilot
python -m pip install -r requirements.txt
ollama pull qwen3:4b
python run.py
```

1. A QR code appears (in the terminal and as an image).
2. Scan it with your phone camera and open the link. Or, on Android, scan it with the [PocketPilot app](#android-app) instead (then skip step 3).
3. The first time, the phone says the connection **isn't private**. That's expected: PocketPilot makes its own certificate on your laptop. Tap **Advanced → Proceed** (or [remove the warning for good](#optional-remove-the-not-private-warning-recommended)).
4. If Windows asks about the firewall, allow **Private networks** only.
5. Optional: in your phone browser menu, choose **Add to Home screen** so it opens like an app.

The first start downloads the speech model (about 145 MB) and the wake-word model (about 5 MB); `qwen3:4b` is about 2.5 GB. The first Telugu command downloads the Telugu speech model (about 250 MB). After that everything works offline, except web skills like weather and search.

Optional settings: copy `.env.example` to `.env` (home city for "weather", the WhatsApp names you use most, free keys for news and cricket).

| Command | What it does |
| --- | --- |
| `python run.py` | Start (or double-click `start.bat`) |
| `python run.py --no-wake` | No laptop microphone ("Hey Jarvis" off) |
| `python run.py --no-voice` | Touchpad only |
| `python run.py --http` | Plain HTTP (touchpad works, the phone mic doesn't) |
| `python run.py --new-token` | Unpair every phone and make a new QR code |

For screen descriptions ("what's on my screen?") also run `ollama pull qwen3.5:4b` (a model that can see images).

### Optional: remove the "not private" warning (recommended)
PocketPilot runs over **HTTPS**, because phones only allow the microphone on secure pages. It makes its own certificates in `data/`, for free.

To make your phone trust them for good (Android):
1. On the phone, open `https://<laptop-ip>:8765/pocketpilot-ca.crt` (the exact link is printed in the terminal) and download it.
2. Go to **Settings → Security → More security settings → Install from device storage → CA certificate** (wording varies by phone), and pick the downloaded file.
3. Reopen PocketPilot: no warning, and Add to Home screen works like a real app.

This certificate can **only** vouch for home-network addresses (192.168.x.x, 10.x.x.x, 172.16–31.x.x) and `localhost`, so it can't be used to fake real websites. If you change Wi-Fi, PocketPilot makes a new server certificate automatically and the phone keeps trusting it. You can remove it any time in the same Settings screen.

## Android app

The same phone remote as an installable Android app (Android 7.0 or newer). It shows exactly the page a
browser shows (touchpad, voice, Approve cards, Telugu) and adds what a browser can't do:

- **No "not private" warning:** the QR code carries a fingerprint of your laptop's own certificate. The app
  downloads the certificate once, keeps it only if the fingerprint matches, and then connects only to a
  laptop whose certificate it signed. Nothing else is trusted.
- **Finds the laptop again** when its Wi-Fi address changes (a small broadcast on the Wi-Fi; the laptop
  answers only your paired phone, and the pairing token never goes over the air).
- **Speaks replies with the phone's own voice**, Telugu included, and vibrates on taps.
- The phone's **back button** opens a menu: Reload, Find the laptop again, Pair again.

**Install:** download `PocketPilot.apk` from the [Releases page](https://github.com/Vardhansaigadde/PocketPilot/releases)
on your phone, open it, and allow "install from this source" when Android asks. Then start
`python run.py` on the laptop and scan its QR code with the app.

**Build it yourself** (free: Flutter SDK + Android Studio): `cd android_app`, then `flutter build apk --release`.
The code is in [`android_app/`](android_app/).

### If the phone can't connect
- Phone and laptop must be on the same Wi-Fi. College and public Wi-Fi often block devices from talking to each other: use your **phone's hotspot** and connect the laptop to it.
- Make sure the Windows Firewall prompt was allowed for Private networks. If you dismissed it, open *Windows Security → Firewall → Allow an app* and tick Python for Private.
- Check the network is set to *Private* in Windows Wi-Fi settings, not *Public*.
- After updating from an older version, the address changed from `http://` to `https://`: scan the QR code once more.

## Touchpad

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

## Voice commands

Hold the **mic** on the phone and speak, or **slide it right to lock** and talk hands-free, then tap ✓ to send (slide left to cancel, like a WhatsApp voice note). You can also type in the command box, or say **"Hey Jarvis"** to the laptop and then your command. The reply shows on the phone and is spoken out loud.

| Say | What happens |
| --- | --- |
| "scroll down", "scroll up a lot", "click", "right click", "double click" | Mouse |
| "type hello world", "press enter", "copy", "paste", "undo", "select all" | Keyboard |
| "volume up", "mute", "pause", "next song" | Media keys |
| "switch app", "show desktop" | Windows shortcuts |
| "open Chrome / Edge / Notepad / Calculator / File Explorer / Settings / WhatsApp / Spotify / VS Code / Paint / Word / Excel / PowerPoint / Camera" | Opens that app |
| "close the window" | Asks **Approve** on the phone first |
| "show grid" → "click 14" | 96 numbered boxes over the screen; clicks the middle of box 14 |
| "zoom 14" → "click 5" | Splits box 14 into 9 smaller boxes for tiny buttons, then clicks one |
| "weather", "weather in Hyderabad", "when is sunset" | Open-Meteo forecast |
| "air quality in Delhi" | AQI + simple advice |
| "who is APJ Abdul Kalam", "tell me about the Taj Mahal" | Short Wikipedia summary |
| "convert 100 dollars to rupees", "dollar rate" | Today's exchange rate (Frankfurter, no key) |
| "define serendipity", "what does ephemeral mean" | Dictionary meaning + example (no key) |
| "news", "news about ISRO" | Top headlines (free key from gnews.io in `.env`) |
| "cricket score" | Live scores (free key from cricketdata.org in `.env`) |
| "search YouTube for lofi", "search Amazon for a wireless mouse", "search GitHub for pocketpilot" | Opens the search results |
| "play Dude", "play the song Kesariya" | Finds the song on YouTube |
| "play Dude on Spotify" | Spotify search (in the Spotify app if installed, otherwise the Spotify web player) |
| "go to GitHub", "open ChatGPT", "visit CodeChef", "go to github.com/Vardhansaigadde/PocketPilot" | Opens that website (40 popular sites by name, or any address) |
| "ask ChatGPT how to reverse a list in Python" | Opens ChatGPT with your question |
| "new tab", "next tab", "go back", "refresh", "address bar" | Browser shortcuts |
| "close this tab", "reopen closed tab" | Closes the tab in a browser, Notepad or VS Code (never presses Ctrl+W in other apps, where it could close the whole window). Unsaved Notepad tabs: it tells you Notepad is asking to save and never answers for you |
| "search for cricket score", "go to github" (with a browser in front) | Opens it in a **new tab of the browser you are using** (Chrome, Edge, Firefox...). With no browser in front it opens Edge |
| "open Edge **then** type github.com **then** press enter" | Runs up to 5 commands in order, waiting for windows to open |
| "open notepad and write my shopping list: milk, eggs and bread" | The AI plans simple steps once, then runs them one by one (shown on the phone) |
| "what did I do today?", "what was I working on yesterday?" | Answers from a local history log (`data/history.db`, never uploaded); "clear my history" deletes it |
| "open my laptop", "wake up" | Turns the laptop screen back on (if it's locked, unlock with face, fingerprint or PIN) |
| "keep my laptop awake", "let my laptop sleep" | While PocketPilot runs it stops the laptop sleeping **when plugged in** (default), always, or never |
| "stop" (or the **■** button) | Cancels everything |

Common phrases are matched instantly without AI (about 0.5 s from the phone mic). Anything else ("I want to listen to some lofi") goes to a small AI model running on your laptop through Ollama, which can only answer with one of the actions above. The model loads in the background when PocketPilot starts (up to a minute on a CPU), so it's ready by the time you speak. Apps that aren't installed (Spotify, WhatsApp) open their website instead.

Multi-step tasks use **plan once, then run simple commands**: the AI turns your request into a short list like "open notepad", "type …", and each step goes through the normal checks (allow-list, blocked apps, Approve). An earlier "look, decide, act" loop was tested and dropped: on a CPU the 4B model took about 15 s per step and lost track of what it had done.

**Why keep-awake instead of waking from sleep?** While the laptop sleeps Windows pauses PocketPilot too, and a phone browser can't send Wake-on-LAN packets. So by default PocketPilot asks Windows not to sleep while it's charging (the screen still turns off), and "open my laptop" turns the screen back on. Nothing in Windows' settings is changed, and the request ends when PocketPilot stops. `POCKETPILOT_KEEP_AWAKE=always|charging|off` in `.env`.

**When it mishears you.** Speech-to-text guesses names it doesn't know ("Kidduuu" came out as "Kid do" and "Kitya", "Amma" as "a month"). PocketPilot fixes this in four ways:
- It remembers the chat names it sees in WhatsApp (`data/known_names.json`, never uploaded) and gives them to Whisper as hints, so it hears them better next time.
- A name that isn't found but *sounds like* one of your chats gets a question instead of an error: "I couldn't find Kitya. Did you mean 1) Kidduuu 🎀?" Say "one" to carry on.
- Common English mishearings of family names ("a month", "your mom", "Amah") try Amma.
- Known slips are corrected before matching: "grid hub" → GitHub, "play dude in what's Spotify" → Spotify.

The phone always shows what it heard in quotes, so you can see what went wrong.

**Wake word.** The laptop mic listens for **"Hey Jarvis"** by default. `POCKETPILOT_WAKE_WORD` in `.env` can switch it to another ready-made one (`alexa`, `hey_mycroft`, `hey_rhasspy`) or to your own: train a model such as "Hey Pilot" with openWakeWord's free training notebook (runs on Google Colab, about an hour), put the `.onnx` file in `data/`, and set `POCKETPILOT_WAKE_WORD=hey_pilot.onnx`.

## Smart click and the screen

| Say | What happens |
| --- | --- |
| "click the Sign in button", "click Downloads", "right click on Documents", "double click My Pictures" | Finds that button, link or tab by its name and clicks it |
| "accept the cookies popup", "reject cookies" | Clicks the cookie banner's button, whatever the site calls it (Accept all / I agree / Allow, or Reject all / Decline / Necessary only) |
| "play the second video", "open the first result", "click the 3rd link", "open the last result", "రెండో వీడియో ప్లే చెయ్యి" | On YouTube, Google or Bing: counts the videos or results **you can see right now**, top to bottom, and opens that one. Ads, the AI answer box and menus are skipped. After scrolling, "the second video" is the second one on screen |
| "what's on my screen?" | Describes the screen (vision model, about 40 s) |
| "summarize this page" | 2-3 sentence summary of the page you're on (about 30-40 s) |
| "explain this error" | What the error on screen means and how to fix it (a few seconds) |
| "read the screen" | Reads the visible text out loud (instant) |

How smart click finds things: first Windows **UI Automation** (the same list of buttons screen readers use, about 0.2 s), then Windows' built-in **OCR** (reads the text on screen, about 0.3 s) if the app doesn't share its buttons. If neither finds it, it says so and you can use the numbered grid. Names are matched the way speech-to-text hears them ("kidd u" finds the chat "Kidduuu", "log in" finds "Login"), but never across opposite words ("show" never clicks "Hide"); a close match is reported as "(closest match)". Very large windows, like a long WhatsApp chat, switch to OCR after 2 seconds. Buttons like Send, Delete, Pay or Sign in always wait for **Approve** on the phone.

The screen explainer reads the window's text with Windows OCR and asks the local text model; "what's on my screen" sends a small screenshot to the local vision model (`qwen3.5:4b`). Screenshots stay in memory: never saved, never sent anywhere.

## WhatsApp

| Say | What happens |
| --- | --- |
| "message amma that I'll be late", "reply to Kidduuu saying OK" | Opens the chat and types the message; **sends only after you tap Approve** (Cancel clears the draft) |
| "call amma", "video call amma on WhatsApp" | Opens the chat; **calls only after Approve** |
| "open my chat with amma" | Opens the chat |

WhatsApp Desktop is driven through its own button names (UI Automation), not by guessing where to click. Before sending or calling it checks that the chat header really is the person you named, and again right before it presses Enter or the call button. It never types unless WhatsApp is really in front.

Two chats with the same name ("Amma ❤️" and "Amma")? It never guesses: it asks you to say **"amma heart"** or **"just amma"** (common emoji have spoken names: heart, ribbon, star, flower, crown...), or the number from the list, and the Approve card always shows the exact contact, emoji included. To make plain "amma" mean the ❤️ one, put `POCKETPILOT_CONTACTS=Amma ❤️` in `.env`; names listed there are also given to the speech model so it hears them right. Common Telugu family names (Amma, Nanna, Akka, Anna...) are known out of the box.

## Telugu

Tap **EN** next to the command box so it shows **తె**, then speak Telugu, or Telugu mixed with English. Replies come back in Telugu and the phone speaks them. Typed Telugu works with either setting.

| Say | What happens |
| --- | --- |
| "నోట్‌ప్యాడ్ ఓపెన్ చెయ్యి", "notepad open cheyyi" | Opens Notepad |
| "అమ్మకి కాల్ చెయ్యి", "ammaki call cheyyi" | Approve card for a WhatsApp call to Amma |
| "అక్కకి హాయ్ అని మెసేజ్ పంపు" | Drafts "హాయ్" to Akka, sends after Approve ("రెండు" picks the 2nd Akka) |
| "హైదరాబాద్‌లో వాతావరణం ఎలా ఉంది" | Hyderabad weather, answered in Telugu |
| "యూట్యూబ్‌లో తెలుగు పాటలు పెట్టు" | YouTube search for తెలుగు పాటలు |
| "రెండో వీడియో ప్లే చెయ్యి", "ట్యాబ్ క్లోజ్ చెయ్యి" | The second video on screen; close the tab |
| "వాల్యూమ్ పెంచు", "కిందకి స్క్రోల్ చెయ్యి", "స్క్రోల్ డౌన్", "ఆపు" | Volume, scrolling, stop |

How it works: a Telugu-trained Whisper model (IIT Madras' Telugu Whisper-small, Apache-2.0) turns speech into Telugu text. Common commands are matched by Telugu phrase rules in `agent/telugu.py` (instant, no AI): it strips Telugu case endings (అమ్మ**కి**), turns Telugu-script English words back into English (స్క్రోల్ డౌన్ → scroll down) and maps family and city names (అక్క → Akka, హైదరాబాద్ → Hyderabad). Anything else goes to the local AI with a transliterated hint. Replies use Telugu templates; the phone's own Android voice speaks them, because Windows has no Telugu voice. On a CPU it takes 3–5 s for a 6–10 s sentence, with 2–10 % character errors on clear Telugu speech.

## How it works

```mermaid
flowchart LR
    subgraph Phone["Phone (browser app)"]
        T[Touchpad + keyboard]
        M[Mic / text box]
        A[Approve card]
    end
    subgraph Laptop["Laptop (Python, all local)"]
        S["Server (FastAPI)<br/>pairing token + allow-list"]
        W["Whisper<br/>speech to text"]
        R["Instant phrases<br/>English + Telugu"]
        L["Local AI (Ollama)<br/>answers only in the command format"]
        E["Executor<br/>mouse, keys, apps, skills"]
        U["UI Automation + OCR<br/>finds buttons, results, chats"]
    end
    T -- "wss, same Wi-Fi" --> S
    M -- audio / text --> S --> W --> R
    R -- unknown phrase --> L --> E
    R --> E
    E <--> U
    E -- "send, call, close, delete" --> A
    A -- Approve --> E
```

- **web/**: the phone app (plain HTML + JavaScript, no framework). Touches are batched to at most one message per screen frame to keep lag low.
- **server/**: `protocol.py` (every message must match a fixed schema; unknown actions, huge movements and risky shortcuts are rejected before anything moves), `pairing.py` (the random token in the QR code), `certs.py` (a small local certificate authority, so the phone can use its mic over HTTPS), `input_control.py` (real mouse and keyboard, released safely if the phone disconnects mid-drag).
- **agent/**: the assistant.
  - Understanding: `commands.py` (every allowed action), `router.py` (instant English phrases), `telugu.py` (Telugu rules and replies), `llm.py` (Ollama), `stt.py` (Whisper), `names.py` (learned WhatsApp names, sound-alike matching).
  - Doing: `executor.py`, `approvals.py`, `apps.py` (the only apps it can open), `windows.py` (bring windows forward, which app is in front), `grid.py`, `smart_click.py` (UI Automation + OCR), `results.py` (the nth result or video on screen), `whatsapp.py`, `task_agent.py` (plan-once tasks), `screen.py` + `explainer.py` (reading the screen), `memory.py` (history log), `laptop_voice.py` (wake word).
- **skills/**: weather, air quality, Wikipedia, web search, websites, currency, dictionary (no keys); news and cricket (free keys).
- **android_app/**: the Android app (Flutter). It shows the phone page in Android's web view and adds certificate pinning (`trust.dart` + `MainActivity.kt`), QR pairing, finding the laptop (`discovery.dart`, with `server/discovery.py` on the laptop), and speech/vibration (`web/native.js`).

## Safety

- Only devices with the pairing token can connect; the server is meant for your home Wi-Fi only.
- Everything between phone and laptop is encrypted (HTTPS / secure WebSocket), so others on the Wi-Fi can't read your typing or steal the pairing token. Private keys stay in `data/` and are never sent to the phone.
- The phone can only trigger actions on a fixed allow-list. It cannot run programs or commands.
- The AI model never runs anything itself: its answer must match the command format exactly, or nothing happens. It can only open apps from a fixed list (no terminal, no PowerShell), and searches only open a results page.
- Closing a window, sending a WhatsApp message, making a call, and clicking buttons like Send, Delete, Pay, Sign in, Close, Exit or End call all wait for **Approve** on the phone, and cancel themselves after 30 seconds.
- Voice audio is processed on the laptop and never saved. The web skills (weather, air quality, Wikipedia, currency, dictionary, news, cricket) send only the place, topic, word or currency they need.
- Websites always open as `https://` pages. Files, scripts and other kinds of links are refused.
- Kill switch: the **■** button, saying "stop", or **Ctrl+C** in the terminal.

## How well it works

Real tasks run end to end on a CPU-only laptop (Intel i5-12450H, 16 GB RAM, no GPU), 3 runs each, with `python scripts/eval_agent.py`:

**54 / 57 tasks succeeded (95%)**

| Group | Tasks | Success |
| --- | --- | --- |
| English | Notepad typing, Calculator sums planned by the local AI, websites, searches, currency, dictionary | 24/24 |
| WhatsApp | message and call Amma (stops at the Approve card, which the eval cancels), "Did you mean Kidduuu?" | 9/9 |
| Telugu | open Notepad, YouTube songs, Hyderabad weather, call / message Amma, in Telugu script and Tenglish | 15/15 |
| Screen | open the first search result, close a tab, play the second video | 6/9 |

Full table with times: [docs/eval.md](docs/eval.md). Nothing is sent, called, bought or deleted during the eval.

The three misses were all "play the second video": YouTube puts ads between results, and in those runs only one real video was on screen, so PocketPilot said "I can only see 1 video" instead of clicking a guess.

The local AI on its own picks the right command for **32 of 33 open-ended phrases (97%)**, including refusing "transfer 500 rupees", "delete all the files" and "log into my bank account" (`scripts/check_ai.py`; 4 more of the 37 phrases are caught by the instant phrases first). The miss was "accept the cookies popup" (a plain click instead of the Accept button); that phrase is now handled by an instant rule.

## Development

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest
```

Tests use a fake controller, fake internet and a fake AI model, so they never move your real mouse, open apps or need Ollama.

To check the real local AI model on 37 open-ended phrases (including requests it must refuse, like payments or deleting files), with Ollama running:

```powershell
python scripts/check_ai.py
```

It prints which command the model picks for each phrase, how long it took, and the overall accuracy. Nothing is executed.

Phone test checklists for each version: [v2](docs/v2-commands.md), [v3](docs/v3-tests.md), [v4](docs/v4-tests.md), [v5](docs/v5-tests.md).

## Roadmap

| Version | Adds |
| --- | --- |
| **v1 Touchpad** ✅ | Phone touchpad, keyboard, media keys, QR pairing |
| **v2 Voice commands** ✅ | Phone mic + "Hey Jarvis" on the laptop; open apps, weather, search, websites, grid clicking |
| **v3 Smart click + screen explainer** ✅ | "Click the Login button", "summarize this page", "explain this error" |
| **v4 Task agent** ✅ | Multi-step tasks, WhatsApp messages **and calls** with Approve, memory of what you did, currency/dictionary/news/cricket |
| **v5 Telugu** ✅ | Telugu and Telugu–English voice commands, Telugu replies; "the second video", tabs |
| v6 Android app | Installable app: finds the laptop when its address changes, no certificate warning |
| v7 Macros + MCP | "Watch me once" skills, MCP server for other AI apps |

Details: [docs/ROADMAP.md](docs/ROADMAP.md).

## License

MIT
