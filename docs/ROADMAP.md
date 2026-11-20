# PocketPilot roadmap

Launch target: **Feb 14, 2027** (v1–v5), at about 10 hours a week. v6 comes after launch.
A version is done only when its "Done when" checks pass, tests pass, and README is updated.

## v1 — Touchpad ✅ (done)
Phone as touchpad, keyboard and media remote; QR pairing.
- Done when: phone scans QR, moves cursor, clicks, scrolls, types with no noticeable lag.

## v2 — Voice commands ✅ (done, tested on the phone with `docs/v2-commands.md`)
Speak into the phone (mic button) or to the laptop ("Hey Pilot" wake word).
- Speech-to-text: faster-whisper (base/small) on CPU. Wake word: openWakeWord.
- Router: fixed commands matched instantly (fast path); anything else goes to Ollama, which returns a JSON command.
- Commands: scroll up/down, click, type text, volume, open an app (Chrome, Edge, WhatsApp, Notepad...), close the window (asks Approve first), numbered grid mode ("show grid", "click 14").
- Skills (no API key): weather + sunset (Open-Meteo forecast + geocoding), air quality (Open-Meteo Air Quality), Wikipedia summaries, web search (open Edge on a Bing / YouTube / Amazon search page).
- Spoken or on-screen reply on the phone.
- Done when: 25 spoken commands work from phone and laptop mic.

## v3 — Smart click + screen explainer (Dec 14 – Jan 3)
- "Click the Login button": Windows UI Automation (pywinauto) finds controls by name; fallback = screenshot + EasyOCR, then a local vision model (Qwen-VL / LLaVA via Ollama).
- Screen explainer: "what's on my screen?", "summarize this page", "explain this error".
- Done when: smart click hits the right target on 10 test screens; summaries correct on 5 test pages.

## v4 — Task agent + messaging + memory (Jan 4 – Jan 24)
- Agent loop: plan → look → decide → act → check, step limit 15, every step logged to SQLite.
- Messaging: "reply to Ravi that I'll be late" → opens WhatsApp Desktop, drafts, shows the draft on the phone, sends ONLY after Approve.
- Memory: "what was I working on yesterday?" answers from the action log.
- More skills: currency (Frankfurter, no key), dictionary (Free Dictionary API), cricket scores (CricketData.org free key), news (GNews free key). Keys in `.env`.
- Optional cloud fallback: OpenRouter free models (off by default).
- Eval script: 20 tasks × 3 runs → success rate table for README.
- Done when: 5 multi-step tasks finish end to end; no message is ever sent without Approve.

## v5 — Telugu + parent mode (Jan 25 – Feb 7)
- Telugu speech-to-text: AI4Bharat IndicConformer Telugu (int8 ONNX) or Shruti Telugu — test both, keep the better one. Whisper is weak at Telugu.
- Translation: AI4Bharat IndicTrans2 (Telugu → English for the planner, English → Telugu for replies).
- Telugu text-to-speech: OmniVoice or AI4Bharat Indic-TTS. English: Piper.
- Parent mode: simple large-button phone screen, Telugu voice only.
- Native Android app (Flutter) with haptics; APK on GitHub Releases.
- Done when: 20 Telugu commands work, including Telugu mixed with English.

## Launch (Feb 14)
README with demo GIF + eval table, 60–90 s demo video, LinkedIn post.

## v6 — Macros + MCP (after launch, Feb 15 – Mar 14)
- "Watch me once": record a task, turn it into a reusable skill ("do my morning setup").
- MCP server exposing PocketPilot's skills to other AI apps (MCP Python SDK).
- Done when: a recorded task replays correctly 3 times in a row; another AI app can call PocketPilot over MCP.

## Not doing
Focus mode, paid APIs, automatic payments/booking, control over the internet (same Wi-Fi only).
