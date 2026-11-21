"""The laptop server: serves the phone app and listens for its messages."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from fastapi import FastAPI, Response, WebSocket, WebSocketDisconnect, status
from fastapi.staticfiles import StaticFiles

from .input_control import Controller, dispatch
from .pairing import check_token
from .protocol import MAX_AUDIO_BYTES, Approve, BadMessage, Lang, Say, Stop, parse_message

if TYPE_CHECKING:
    from agent.assistant import Assistant

log = logging.getLogger("pocketpilot.server")

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


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
