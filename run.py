"""Start PocketPilot: run this on the laptop, then scan the QR code with your phone.

    python run.py              # normal start
    python run.py --new-token  # unpair every phone and make a new QR code
    python run.py --http       # plain HTTP (no certificates; the phone mic won't work)
    python run.py --no-wake    # voice from the phone only (laptop mic off)
    python run.py --no-voice   # touchpad only
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def main() -> None:
    parser = argparse.ArgumentParser(description="PocketPilot laptop server")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--new-token", action="store_true", help="unpair all phones")
    parser.add_argument("--no-qr-window", action="store_true", help="don't open the QR image")
    parser.add_argument("--http", action="store_true",
                        help="plain HTTP instead of HTTPS (the phone mic won't work)")
    parser.add_argument("--no-voice", action="store_true", help="touchpad only, no voice commands")
    parser.add_argument("--no-wake", action="store_true", help="don't use the laptop mic / wake word")
    parser.add_argument("--model", help="Ollama model name (default qwen3:4b, or POCKETPILOT_MODEL)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
    for noisy in ("httpx", "httpcore", "comtypes", "faster_whisper", "huggingface_hub"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    if sys.platform == "win32":
        # Use real screen pixels, so the grid numbers and mouse positions line up
        # on screens with Windows scaling (125%, 150%...).
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            pass

    try:
        import uvicorn
        from server.input_control import PynputController
        from server.main import create_app
        from server.pairing import get_lan_ip, load_or_create_token, pair_url, show_qr
    except ImportError as exc:
        sys.exit(f"Missing package ({exc.name}). Run:  pip install -r requirements.txt")

    token = load_or_create_token(DATA / "token.txt", rotate=args.new_token)
    ip = get_lan_ip()

    ssl: dict[str, str] = {}
    ca_cert = None
    if not args.http:
        try:
            from server.certs import ensure_certs
        except ImportError as exc:
            sys.exit(f"Missing package ({exc.name}). Run:  pip install -r requirements.txt")
        certs = ensure_certs(DATA, ip)
        ssl = {"ssl_certfile": str(certs.cert), "ssl_keyfile": str(certs.key)}
        ca_cert = certs.ca_cert

    scheme = "http" if args.http else "https"
    url = pair_url(ip, args.port, token, scheme=scheme)

    print("\n  PocketPilot is starting.")
    print("  Scan this QR code with your phone camera (same Wi-Fi as this laptop):\n")
    png = DATA / "pair_qr.png"
    if show_qr(url, png) and not args.no_qr_window and sys.platform == "win32" and png.exists():
        os.startfile(png)  # opens the QR image too, in case the terminal one is hard to scan
    print(f"\n  Or open this on your phone:  {url}")
    if not args.http:
        print("  First time: the phone warns the connection isn't private.")
        print("  Tap Advanced -> Proceed (it's your own laptop), or install the certificate")
        print(f"  once to remove the warning:  https://{ip}:{args.port}/pocketpilot-ca.crt")
    print("  If Windows asks about the firewall, allow PRIVATE networks only.")
    print("  Press Ctrl+C here to stop.\n")

    controller = PynputController()
    assistant = None if args.no_voice else build_assistant(controller, args)
    app = create_app(token=token, controller=controller, ca_cert=ca_cert, assistant=assistant)
    if assistant is not None:
        assistant.notify = app.state.phones.broadcast_from_thread   # "Looking at your screen…"
        if assistant.agent is not None:
            assistant.agent.notify = assistant.notify                # "Step 2: …"

    if assistant is not None and not args.no_wake:
        try:
            from agent.laptop_voice import LaptopVoice

            LaptopVoice(assistant, app.state.phones.broadcast_from_thread).start()
        except ImportError as exc:
            print(f"  Laptop mic off (missing {exc.name}). Phone voice still works.")

    # 0.0.0.0 = reachable from your Wi-Fi; the token keeps other devices out.
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="warning", **ssl)


def build_assistant(controller, args):  # noqa: ANN001, ANN201 - kept simple for run.py
    """Voice assistant: commands, skills, grid, local AI model and Whisper."""
    try:
        from agent.approvals import Approvals
        from agent.assistant import Assistant
        from agent.config import load_config
        from agent.executor import Executor
        from agent.explainer import ScreenExplainer
        from agent.grid import TkGrid
        from agent.llm import OllamaPlanner
        from agent.keep_awake import KeepAwake, screen_locked
        from agent.memory import Memory
        from agent.whatsapp import WhatsApp
        from agent.smart_click import SmartClicker
        from agent.task_agent import TaskAgent
        from agent.stt import WhisperTranscriber
        from skills import WebSkills, make_client
        from skills.web_search import open_in_edge
    except ImportError as exc:
        print(f"  Voice commands off (missing {exc.name}). Run: pip install -r requirements.txt")
        return None

    cfg = load_config(ROOT / ".env")
    from agent.apps import is_available
    from agent.executor import start_app

    skills = WebSkills(make_client(contact=cfg.contact), open_in_edge, home_city=cfg.home_city,
                       open_app_link=start_app, app_available=is_available,
                       gnews_key=cfg.gnews_key, cricket_key=cfg.cricket_key,
                       amazon_domain=cfg.amazon_domain)
    planner = OllamaPlanner(args.model or cfg.model, cfg.ollama_url)
    explainer = ScreenExplainer(planner.model, cfg.vision_model, cfg.ollama_url,
                                after=planner.warm_up)   # get the command model ready again afterwards
    awake = KeepAwake(cfg.keep_awake)       # no sleep while charging, so the phone can always connect
    awake.start()
    memory = Memory(DATA / "history.db")   # local only; "clear my history" deletes it
    clicker = SmartClicker()
    executor = Executor(controller, Approvals(), skills=skills, grid=TkGrid(),
                        clicker=clicker, screen=explainer,
                        memory=memory, summarize=explainer.summarize_history,
                        whatsapp=WhatsApp(controller, contacts=list(cfg.contacts)),
                        awake=awake, locked=screen_locked)
    planner.warm_up()
    transcriber = WhisperTranscriber(cfg.whisper_model, names=cfg.contacts,
                                     telugu_model=cfg.telugu_whisper)
    transcriber.preload()
    print(f"  Voice: Whisper {cfg.whisper_model}, AI model {planner.model} (Ollama)"
          + (", laptop mic: say \"Hey Jarvis\"" if not args.no_wake else ""))
    assistant = Assistant(executor, planner=planner, transcriber=transcriber, memory=memory)
    assistant.agent = TaskAgent(plan=planner.plan_steps, to_command=assistant.to_command, act=assistant.act)
    return assistant


if __name__ == "__main__":
    main()
