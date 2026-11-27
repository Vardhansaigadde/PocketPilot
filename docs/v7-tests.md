# v7 test checklist: MCP

Keep `python run.py` running and the phone connected.

| # | Do | Expected | ✓ |
|---|----|----------|:-:|
| 1 | `npx @modelcontextprotocol/inspector python pocketpilot_mcp.py` → Connect → List tools | 22 tools | ☐ |
| 2 | Call `weather` with place Hyderabad | Today's weather; the phone shows "AI app: …" | ☐ |
| 3 | Call `open_app` notepad | Notepad opens | ☐ |
| 4 | Call `whatsapp_message` (a contact, "test") | Approve card on the phone; **Cancel** = nothing sent | ☐ |
| 5 | Call `whatsapp_message` with a name that matches two chats | "Which …?" with the options; nothing typed | ☐ |
| 6 | Stop `python run.py`, call `weather` | "PocketPilot isn't running… Start it first" | ☐ |
| 7 | *(optional, not run)* Chat app (Ollama, qwen3:4b) with the MCP server added: "What's the weather in Hyderabad? Then open Notepad." | It calls `weather` and `open_app`; both happen | ☐ |
| 8 | *(optional, not run)* In the chat app: "send hi to Amma on WhatsApp" | Only an Approve card on the phone; the app says to check the phone | ☐ |
