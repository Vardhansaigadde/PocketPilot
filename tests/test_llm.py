"""The Ollama planner, tested against a fake Ollama server (httpx.MockTransport)."""

import json

import httpx
import pytest

from agent.assistant import PlannerError
from agent.commands import OpenAppCmd, UnknownCmd
from agent.llm import OllamaPlanner


def planner(*responses, seen=None):
    queue = list(responses)

    def handler(request):
        if seen is not None:
            seen.append(json.loads(request.content))
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, int):
            return httpx.Response(item, text="error")
        return httpx.Response(200, json={"message": {"role": "assistant", "content": item}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OllamaPlanner("qwen3:4b", client=client)


def test_valid_answer_becomes_a_command():
    seen = []
    cmd = planner('{"action": "open_app", "app": "calculator"}', seen=seen).to_command("do maths")
    assert cmd == OpenAppCmd(action="open_app", app="calculator")
    body = seen[0]
    assert body["model"] == "qwen3:4b" and body["stream"] is False and body["think"] is False
    assert isinstance(body["format"], dict)            # forced to the command shape
    assert "discriminator" not in json.dumps(body["format"])
    assert body["messages"][-1] == {"role": "user", "content": "do maths"}


@pytest.mark.parametrize("content", [
    "not json at all",
    '{"action": "run_shell", "cmd": "del *"}',
    '{"action": "open_app", "app": "cmd.exe"}',
    '{"action": "open_app", "app": "notepad", "path": "C:/x.exe"}',
    "[]",
])
def test_bad_answers_never_become_actions(content):
    cmd = planner(content).to_command("anything")
    assert isinstance(cmd, UnknownCmd)


def test_unknown_with_reason_is_kept():
    cmd = planner('{"action": "unknown", "say": "I can\'t make payments."}').to_command("pay bill")
    assert cmd.say == "I can't make payments."


def test_ollama_not_running():
    with pytest.raises(PlannerError, match="Is Ollama running"):
        planner(httpx.ConnectError("refused")).to_command("hi")


def test_model_not_downloaded():
    with pytest.raises(PlannerError, match="ollama pull qwen3:4b"):
        planner(404).to_command("hi")


def test_400_retries_in_plain_json_mode():
    seen = []
    cmd = planner(400, '{"action": "stop"}', seen=seen).to_command("halt")
    assert cmd.action == "stop"
    assert seen[1]["format"] == "json" and "think" not in seen[1]


def test_timeout():
    with pytest.raises(PlannerError, match="too long"):
        planner(httpx.ReadTimeout("slow")).to_command("hi")
