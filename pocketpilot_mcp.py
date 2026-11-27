"""PocketPilot as an MCP server: other AI apps can use PocketPilot's actions (v7).

MCP (Model Context Protocol) is the standard way AI apps call tools. An MCP-compatible
chat app (for example one running a local model through Ollama) starts this file and can
then open apps, search, check the weather, read the screen, click buttons, and draft
WhatsApp messages on this laptop.

It is only a bridge: every call goes to the running PocketPilot (`python run.py`) on this
laptop, so the same rules apply as on the phone. Only allowed actions, and sending a
message, calling, closing or deleting always waits for Approve on the phone. An AI app
can never approve anything itself.

Add it to an MCP app as a stdio server:   python <path to>\\pocketpilot_mcp.py
Test it with the MCP Inspector:          npx @modelcontextprotocol/inspector python pocketpilot_mcp.py
"""

from __future__ import annotations

import os
import ssl
from pathlib import Path
from typing import Any, Literal

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
PORT = int(os.environ.get("POCKETPILOT_PORT", "8765"))

NOT_RUNNING = "PocketPilot isn't running on this laptop. Start it first:  python run.py"
APPROVE_NOTE = (" (This is waiting for the user to tap Approve on their phone. You cannot approve it; "
                "tell the user to check their phone.)")

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=True)       # only looks things up
ACTS = ToolAnnotations(read_only_hint=False, destructive_hint=False)         # changes what's on screen
NEEDS_APPROVE = ToolAnnotations(read_only_hint=False, destructive_hint=True)  # waits for Approve


class PocketPilotLink:
    """Talks to the running PocketPilot over HTTPS on 127.0.0.1 (its local API)."""

    def __init__(self, transport: httpx.BaseTransport | None = None, data_dir: Path = DATA,
                 port: int = PORT) -> None:
        self.data_dir, self.port = data_dir, port
        self.transport = transport

    def _client(self) -> httpx.Client:
        if self.transport is not None:                    # tests
            return httpx.Client(transport=self.transport, base_url="https://127.0.0.1")
        ca = self.data_dir / "pocketpilot-ca.crt"
        verify: Any = ssl.create_default_context(cafile=str(ca)) if ca.exists() else True
        return httpx.Client(base_url=f"https://127.0.0.1:{self.port}", verify=verify, timeout=120)

    def _token(self) -> str | None:
        path = self.data_dir / "token.txt"
        return path.read_text(encoding="utf-8").strip() if path.exists() else None

    def post(self, path: str, payload: dict) -> str:
        """Send it and return what PocketPilot said, as text for the AI app."""
        token = self._token()
        if not token:
            return NOT_RUNNING
        try:
            with self._client() as client:
                r = client.post(path, json=payload, headers={"Authorization": f"Bearer {token}"})
        except httpx.ConnectError:
            return NOT_RUNNING
        except httpx.HTTPError as exc:
            return f"Couldn't reach PocketPilot: {exc}"
        try:
            body = r.json()
        except ValueError:
            return f"PocketPilot answered with an error ({r.status_code})."
        text = str(body.get("reply") or "Done.")
        if body.get("choices"):
            text += " Options: " + "; ".join(map(str, body["choices"])) + "."
        if body.get("needs_approval"):
            text += APPROVE_NOTE
        return text

    def run(self, action: str, **fields: Any) -> str:
        return self.post("/api/run", {"command": {"action": action, **{k: v for k, v in fields.items()
                                                                        if v is not None}}})

    def say(self, text: str) -> str:
        return self.post("/api/say", {"text": text})


def create_server(link: PocketPilotLink | None = None) -> MCPServer:
    link = link or PocketPilotLink()
    mcp = MCPServer(
        name="PocketPilot",
        instructions=("Controls the user's Windows laptop through PocketPilot. Use the specific tools when one "
                      "fits; otherwise use `pocketpilot` with a short plain-English instruction. Messages and "
                      "calls are only drafted: the user must tap Approve on their phone."),
    )

    # -- anything -----------------------------------------------------------------------
    @mcp.tool(annotations=ACTS)
    def pocketpilot(instruction: str) -> str:
        """Tell PocketPilot what to do in plain words, as you would say it to a voice assistant.
        Examples: "open notepad and type hello", "scroll down", "volume up", "go back",
        "close this tab", "ammaki call cheyyi" (Telugu works too). Use the other tools when one fits."""
        return link.say(instruction)

    # -- apps and the web -----------------------------------------------------------------
    @mcp.tool(annotations=ACTS)
    def open_app(app: Literal["chrome", "edge", "notepad", "calculator", "files", "settings", "whatsapp",
                              "spotify", "vscode", "paint", "word", "excel", "powerpoint", "camera"]) -> str:
        """Open an app on the laptop."""
        return link.run("open_app", app=app)

    @mcp.tool(annotations=ACTS)
    def open_website(site: str) -> str:
        """Open a website in the browser, by name ("github", "youtube", "codechef") or address
        ("github.com/someone/project")."""
        return link.run("goto", site=site)

    @mcp.tool(annotations=ACTS)
    def web_search(query: str, site: Literal["google", "bing", "youtube", "amazon", "github", "spotify"] = "google"
                   ) -> str:
        """Search the web (or YouTube, Amazon, GitHub, Spotify) and open the results page."""
        return link.run("search", site=site, query=query)

    # -- answers (read only) ------------------------------------------------------------------
    @mcp.tool(annotations=READ_ONLY)
    def weather(place: str | None = None) -> str:
        """Current weather, today's high/low, chance of rain and sunset. No place = the user's home city."""
        return link.run("weather", place=place)

    @mcp.tool(annotations=READ_ONLY)
    def air_quality(place: str | None = None) -> str:
        """Air quality (AQI) and simple advice for a city."""
        return link.run("air_quality", place=place)

    @mcp.tool(annotations=READ_ONLY)
    def wikipedia(topic: str) -> str:
        """A short Wikipedia summary of a person, place or thing."""
        return link.run("wiki", topic=topic)

    @mcp.tool(annotations=READ_ONLY)
    def define_word(word: str) -> str:
        """The dictionary meaning of an English word, with an example."""
        return link.run("define", word=word)

    @mcp.tool(annotations=READ_ONLY)
    def convert_currency(amount: float, from_currency: str, to_currency: str) -> str:
        """Convert money with today's exchange rate. Currencies as codes: USD, INR, EUR, GBP..."""
        return link.run("currency", amount=amount, from_cur=from_currency.upper(), to_cur=to_currency.upper())

    @mcp.tool(annotations=READ_ONLY)
    def news(topic: str | None = None) -> str:
        """Top news headlines, optionally about a topic."""
        return link.run("news", topic=topic)

    @mcp.tool(annotations=READ_ONLY)
    def history(period: Literal["today", "yesterday", "last_hour", "this_week"] = "today") -> str:
        """What the user did with PocketPilot in that period (from the laptop's local history)."""
        return link.run("memory", period=period)

    # -- the screen ---------------------------------------------------------------------------
    @mcp.tool(annotations=READ_ONLY)
    def read_screen(mode: Literal["read", "summarize", "explain_error", "describe"] = "read") -> str:
        """Look at the laptop screen: read its text, summarize the page, explain an error on it,
        or describe it (describe is slow, about 40 s)."""
        return link.run("screen", mode=mode)

    @mcp.tool(annotations=ACTS)
    def click(target: str, button: Literal["left", "right"] = "left", double: bool = False) -> str:
        """Click a button, link or tab on the screen by its name ("Sign in", "Downloads").
        Risky buttons (Send, Delete, Pay...) wait for Approve on the phone."""
        return link.run("click_on", target=target, button=button, count=2 if double else 1)

    @mcp.tool(annotations=ACTS)
    def open_result(n: int, kind: Literal["result", "video", "link"] = "result") -> str:
        """Open the nth search result or YouTube video visible on screen (1 = first, -1 = last)."""
        return link.run("open_result", n=n, kind=kind)

    @mcp.tool(annotations=ACTS)
    def scroll(direction: Literal["up", "down"], amount: int = 5) -> str:
        """Scroll the window under the mouse."""
        return link.run("scroll", direction=direction, amount=max(1, min(amount, 50)))

    @mcp.tool(annotations=ACTS)
    def type_text(text: str) -> str:
        """Type text into whatever has focus on the laptop (it does not press Enter)."""
        return link.run("type", text=text)

    @mcp.tool(annotations=ACTS)
    def press_key(key: Literal["enter", "backspace", "delete", "tab", "esc", "space", "up", "down", "left",
                               "right", "home", "end", "page_up", "page_down"]) -> str:
        """Press one key."""
        return link.run("key", key=key)

    @mcp.tool(annotations=ACTS)
    def media(key: Literal["volume_up", "volume_down", "mute", "play_pause", "next", "prev"]) -> str:
        """Volume and music controls."""
        return link.run("media", key=key)

    @mcp.tool(annotations=ACTS)
    def brightness(change: Literal["up", "down", "set"], level: int | None = None) -> str:
        """Laptop screen brightness: up / down by 10 %, or set to a level from 5 to 100 (with change="set")."""
        return link.run("brightness", change=change, level=level)

    # -- WhatsApp (always waits for Approve on the phone) --------------------------------------
    @mcp.tool(annotations=NEEDS_APPROVE)
    def whatsapp_message(contact: str, text: str) -> str:
        """Draft a WhatsApp message to a contact. It is NOT sent until the user taps Approve on their phone."""
        return link.run("whatsapp", contact=contact, kind="message", text=text)

    @mcp.tool(annotations=NEEDS_APPROVE)
    def whatsapp_call(contact: str, video: bool = False) -> str:
        """Start a WhatsApp voice or video call. It only rings after the user taps Approve on their phone."""
        return link.run("whatsapp", contact=contact, kind="video_call" if video else "voice_call")

    @mcp.tool(annotations=ACTS)
    def stop() -> str:
        """Stop everything PocketPilot is doing and cancel waiting Approve cards."""
        return link.run("stop")

    return mcp


if __name__ == "__main__":
    import logging

    logging.getLogger("httpx").setLevel(logging.WARNING)   # no "HTTP/1.1 200 OK" lines in the app's log
    create_server().run("stdio")
