"""The laptop server: serves the phone app and listens for its messages."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from fastapi import FastAPI, Request, Response, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .input_control import Controller, dispatch
from .pairing import check_token
from .protocol import MAX_AUDIO_BYTES, Approve, BadMessage, Brightness, Lang, Say, Stop, parse_message

from agent.commands import BadCommand, parse_command

if TYPE_CHECKING:
    from agent.assistant import Assistant

log = logging.getLogger("pocketpilot.server")

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
LOCAL_HOSTS = ("127.0.0.1", "::1")   # the local API (MCP bridge) only answers this laptop


class Phones:
    """Every connected phone, so assistant replies reach all of them."""

    def __init__(self) -> None:
        self._sockets: set[WebSocket] = set()
        self.loop: asyncio.AbstractEventLoop | None = None

    def add(self, ws: WebSocket) -> None:
        self._sockets.add(ws)

    def remove(self, ws: WebSocket) -> None:
        self._sockets.discard(ws)

    def __len__(self) -> int:
        return len(self._sockets)

    async def broadcast(self, messages: list[dict]) -> None:
        for ws in list(self._sockets):
            for m in messages:
                try:
                    await ws.send_json(m)
                except Exception:
                    self._sockets.discard(ws)
                    break

    def broadcast_from_thread(self, messages: list[dict]) -> None:
        """For the laptop-mic thread: hand messages to the server's event loop."""
        if self.loop is not None and self._sockets:
            asyncio.run_coroutine_threadsafe(self.broadcast(messages), self.loop)


def create_app(
    token: str,
    controller: Controller,
    web_dir: Path = WEB_DIR,
    ca_cert: Path | None = None,
    assistant: Assistant | None = None,
    brightness: Any = None,
) -> FastAPI:
    """Build the server. `ca_cert` is the public CA certificate the phone may install."""
    app = FastAPI(title="PocketPilot", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.connections = 0
    phones = Phones()
    app.state.phones = phones

    if ca_cert is not None:
        @app.get("/pocketpilot-ca.crt", include_in_schema=False)
        async def ca_certificate() -> Response:
            # Only the public certificate is ever served, never a private key.
            return Response(ca_cert.read_bytes(), media_type="application/x-x509-ca-cert")

    # ---- local API for other AI apps (v7, MCP bridge: pocketpilot_mcp.py) ---------------
    # Only from this laptop (127.0.0.1) and only with the pairing token. Phones never use it.
    def api_denied(request: Request) -> JSONResponse | None:
        host = request.client.host if request.client else ""
        if host not in LOCAL_HOSTS:
            return JSONResponse({"ok": False, "reply": "Only programs on this laptop can use this."}, 403)
        given = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        if not check_token(given or None, token):
            return JSONResponse({"ok": False, "reply": "Wrong or missing PocketPilot token."}, 401)
        if assistant is None:
            return JSONResponse({"ok": False, "reply": "Voice commands aren't running on the laptop "
                                 "(PocketPilot was started with --no-voice)."}, 503)
        return None

    async def api_result(heard: str, job: Callable[[], list[dict]]) -> dict:
        """Run it like a phone command and show it on the phone too (Approve cards included)."""
        messages = await asyncio.to_thread(job)
        await phones.broadcast([{"t": "heard", "text": f"AI app: {heard}"}, *messages])
        first = next((m for m in messages if m.get("t") == "reply"), {})
        return {
            "ok": bool(first.get("ok", False)),
            "reply": first.get("text", ""),
            "needs_approval": any(m.get("t") == "approve_request" for m in messages),
            "choices": next((m.get("options") for m in messages if m.get("t") == "choices"), None),
        }

    @app.post("/api/run", include_in_schema=False, response_model=None)
    async def api_run(request: Request) -> JSONResponse | dict:
        if (denied := api_denied(request)) is not None:
            return denied
        try:
            body = await request.json()
            cmd = parse_command(body.get("command") if isinstance(body, dict) else None)
        except (BadCommand, ValueError) as exc:
            return JSONResponse({"ok": False, "reply": f"Not an allowed PocketPilot command: {exc}"}, 422)
        heard = ", ".join(f"{v}" for v in cmd.model_dump(exclude_none=True).values())
        return await api_result(heard[:120], lambda: assistant.run_command(cmd, source="mcp"))

    @app.post("/api/say", include_in_schema=False, response_model=None)
    async def api_say(request: Request) -> JSONResponse | dict:
        if (denied := api_denied(request)) is not None:
            return denied
        try:
            body = await request.json()
            text = str(body.get("text", "")).strip()[:300] if isinstance(body, dict) else ""
        except ValueError:
            text = ""
        if not text:
            return JSONResponse({"ok": False, "reply": "Say what PocketPilot should do."}, 422)
        return await api_result(text, lambda: assistant.handle_text(text, source="mcp"))

    async def run_assistant(job: Callable[[], list[dict]]) -> None:
        """Run a slow assistant job in a worker thread, then tell every phone."""
        await phones.broadcast([{"t": "busy", "on": True}])
        try:
            messages = await asyncio.to_thread(job)
        except Exception:
            log.exception("assistant failed")
            messages = [{"t": "reply", "text": "Something went wrong on the laptop.", "ok": False}]
        await phones.broadcast([*messages, {"t": "busy", "on": False}])

    def no_assistant() -> dict:
        return {"t": "reply", "text": "Voice commands aren't running on the laptop.", "ok": False}

    @app.websocket("/ws")
    async def phone_socket(ws: WebSocket) -> None:
        if not check_token(ws.query_params.get("token"), token):
            # 1008 = policy violation: wrong or missing pairing token
            await ws.close(code=status.WS_1008_POLICY_VIOLATION)
            log.warning("refused a connection with a bad token from %s", ws.client)
            return

        await ws.accept()
        phones.loop = asyncio.get_running_loop()
        phones.add(ws)
        app.state.connections += 1
        log.info("phone connected from %s", ws.client)
        await ws.send_json({
            "t": "hello", "name": "PocketPilot", "version": "0.2.0",
            "voice": assistant is not None and assistant.transcriber is not None,
            "assistant": assistant is not None,
        })
        tasks: set[asyncio.Task] = set()

        def background(job: Callable[[], list[dict]]) -> None:
            task = asyncio.create_task(run_assistant(job))
            tasks.add(task)
            task.add_done_callback(tasks.discard)

        try:
            while True:
                frame = await ws.receive()
                if frame["type"] == "websocket.disconnect":
                    break
                audio = frame.get("bytes")
                if audio is not None:
                    if assistant is None:
                        await ws.send_json(no_assistant())
                    elif len(audio) > MAX_AUDIO_BYTES:
                        await ws.send_json({"t": "error", "msg": "recording too long"})
                    else:
                        background(lambda a=audio: assistant.handle_audio(a))
                    continue

                raw = frame.get("text") or ""
                try:
                    msg = parse_message(raw)
                except BadMessage as exc:
                    await ws.send_json({"t": "error", "msg": str(exc)})
                    continue

                if isinstance(msg, Stop):
                    controller.release_all()
                    if assistant is not None:
                        # Straight away, not queued behind a slow command.
                        await phones.broadcast(await asyncio.to_thread(assistant.stop))
                    continue
                if isinstance(msg, Brightness):
                    await ws.send_json(await asyncio.to_thread(_brightness_reply, brightness, msg.change))
                    continue
                if isinstance(msg, Lang):
                    if assistant is not None:
                        await ws.send_json(assistant.set_lang(msg.lang)[0] | {"quiet": True})
                    continue
                if isinstance(msg, (Say, Approve)):
                    if assistant is None:
                        await ws.send_json(no_assistant())
                    elif isinstance(msg, Say):
                        background(lambda m=msg: assistant.handle_text(m.text))
                    else:
                        background(lambda m=msg: assistant.approve(m.id, m.ok))
                    continue

                try:
                    reply = dispatch(msg, controller)
                except Exception:
                    log.exception("action failed: %s", raw[:200])
                    await ws.send_json({"t": "error", "msg": "action failed on the laptop"})
                    continue
                if reply is not None:
                    await ws.send_json(reply)
        except WebSocketDisconnect:
            pass
        finally:
            phones.remove(ws)
            app.state.connections -= 1
            controller.release_all()
            log.info("phone disconnected")

    # Mounted last so /ws above takes priority. html=True serves index.html at "/".
    app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
    return app


def _brightness_reply(brightness: Any, change: str) -> dict:
    """The phone's ☀ buttons work even without voice (python run.py --no-voice)."""
    from agent.brightness import BrightnessError

    if brightness is None:
        return {"t": "reply", "text": "Brightness control isn't available.", "ok": False}
    try:
        return {"t": "reply", "text": f"Brightness {brightness.change(change)}%.", "ok": True, "quiet": True}
    except BrightnessError as exc:
        return {"t": "reply", "text": str(exc), "ok": False}
