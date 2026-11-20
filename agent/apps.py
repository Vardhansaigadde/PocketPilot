"""The only apps PocketPilot can open, and the words people use for them.

Each app maps to a fixed target that Windows knows how to start (a program
name or an app link). The AI can only pick a *name* from this list; it never
supplies a path or a command, so it can't start anything else.
Command prompts, PowerShell and terminals are deliberately not here.
"""

from __future__ import annotations

from typing import Literal, get_args

AppName = Literal[
    "chrome", "edge", "notepad", "calculator", "files", "settings",
    "whatsapp", "spotify", "vscode", "paint", "word", "excel", "powerpoint", "camera",
]

# name -> (what to call it when speaking, what Windows should start)
APPS: dict[str, tuple[str, str]] = {
    "chrome": ("Chrome", "chrome.exe"),
    "edge": ("Edge", "msedge.exe"),
    "notepad": ("Notepad", "notepad.exe"),
    "calculator": ("Calculator", "calculator:"),
    "files": ("File Explorer", "explorer.exe"),
    "settings": ("Settings", "ms-settings:"),
    "whatsapp": ("WhatsApp", "whatsapp:"),
    "spotify": ("Spotify", "spotify:"),
    "vscode": ("VS Code", "vscode:"),
    "paint": ("Paint", "mspaint.exe"),
    "word": ("Word", "winword.exe"),
    "excel": ("Excel", "excel.exe"),
    "powerpoint": ("PowerPoint", "powerpnt.exe"),
    "camera": ("Camera", "microsoft.windows.camera:"),
}

ALIASES: dict[str, str] = {
    "google chrome": "chrome", "chrome browser": "chrome",
    "microsoft edge": "edge", "edge browser": "edge", "browser": "edge", "the browser": "edge",
    "note pad": "notepad", "notes": "notepad",
    "calc": "calculator", "calculator app": "calculator",
    "file explorer": "files", "explorer": "files", "my files": "files", "file manager": "files",
    "this pc": "files", "my computer": "files",
    "windows settings": "settings", "setting": "settings",
    "whats app": "whatsapp", "whatsapp desktop": "whatsapp",
    "vs code": "vscode", "visual studio code": "vscode", "code": "vscode",
    "ms paint": "paint", "microsoft paint": "paint",
    "ms word": "word", "microsoft word": "word",
    "ms excel": "excel", "microsoft excel": "excel",
    "power point": "powerpoint", "microsoft powerpoint": "powerpoint", "ppt": "powerpoint",
    "webcam": "camera", "camera app": "camera",
}

# If the app isn't installed, open its website instead.
WEB_FALLBACK: dict[str, str] = {
    "spotify": "https://open.spotify.com",
    "whatsapp": "https://web.whatsapp.com",
}


def is_available(target: str) -> bool:
    """Is there an app for this target? Only link-style targets ("spotify:") can be checked;
    programs ("notepad.exe") are assumed present and Windows reports if they're not."""
    if not target.endswith(":"):
        return True
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, target[:-1]):
            return True
    except (ImportError, OSError):
        return False


assert set(APPS) == set(get_args(AppName)), "APPS and AppName must list the same apps"


def find_app(words: str) -> str | None:
    """Turn what the user said ("google chrome", "the calculator") into an app name."""
    w = " ".join(words.lower().replace("-", " ").split())
    for prefix in ("the ", "my ", "a "):
        if w.startswith(prefix) and w[len(prefix):] in {**APPS, **ALIASES}:
            w = w[len(prefix):]
    if w.endswith(" app") and w[:-4] in APPS:
        w = w[:-4]
    if w in APPS:
        return w
    return ALIASES.get(w)


def app_label(name: str) -> str:
    return APPS[name][0]


def app_target(name: str) -> str:
    return APPS[name][1]


def app_list_text() -> str:
    return ", ".join(label for label, _ in APPS.values())
