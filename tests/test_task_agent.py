"""Plan-once task agent with a fake planner: steps, and every way it must stop."""

from agent.approvals import Approvals
from agent.assistant import Assistant
from agent.commands import parse_command
from agent.executor import Executor
from agent.router import fast_path
from agent.task_agent import TaskAgent
from tests.test_dispatch import FakeController


def to_command(text):
    return fast_path(text) or parse_command({"action": "unknown", "say": "?"})


def make(steps, max_steps=8):
    ctl, launched = FakeController(), []
    ex = Executor(ctl, Approvals(), launcher=launched.append, app_available=lambda t: True)
    told = []
    agent = TaskAgent(plan=lambda goal: list(steps), to_command=to_command,
                      act=lambda cmd, said: ex.run(cmd), notify=told.extend, max_steps=max_steps,
                      sleep=lambda s: None)
    return agent, ex, ctl, launched, told


def test_runs_the_plan_in_order():
    agent, ex, ctl, launched, told = make(["open notepad", "type hello from pocketpilot", "press enter"])
    say, ok, approval = agent.run("open notepad and type hello from pocketpilot")
    assert ok and approval is None
    assert launched == ["notepad.exe"]
    assert ctl.calls == [("type_text", "hello from pocketpilot"), ("key", "enter")]
    assert say == "Done: Opening Notepad. Typed it. Pressed enter."
    texts = [m["text"] for m in told]
    assert texts[0] == "Plan: 1) open notepad; 2) type hello from pocketpilot; 3) press enter"
    assert texts[1:] == ["Step 1: Opening Notepad.", "Step 2: Typed it.", "Step 3: Pressed enter."]


def test_empty_plan():
    agent, *_ = make([])
    say, ok, _ = agent.run("do something")
    assert not ok and "one by one" in say


def test_stops_at_a_step_it_does_not_understand():
    agent, ex, ctl, launched, _ = make(["open notepad", "do the thing", "press enter"])
    say, ok, _ = agent.run("x")
    assert not ok and "didn't understand step 2" in say and ("key", "enter") not in ctl.calls


def test_stops_at_an_approve_request():
    agent, ex, ctl, *_ = make(["close the window", "type x"])
    say, ok, approval = agent.run("x")
    assert approval is not None and ("type_text", "x") not in ctl.calls


def test_stops_when_a_step_fails():
    agent, *_ = make(["show grid", "click 3"])          # no grid in this executor -> fails
    say, ok, _ = agent.run("x")
    assert not ok and "Step 1 (show grid) didn't work" in say


def test_at_most_max_steps():
    agent, ex, ctl, *_ = make(["scroll down"] * 20, max_steps=3)
    agent.run("x")
    assert ctl.calls.count(("scroll", 0, -5)) == 3


def test_stop_during_a_step_ends_the_task():
    agent, ex, ctl, launched, _ = make(["open notepad", "type never"])
    real_act = agent.act

    def act_then_press_stop(cmd, said):
        agent.cancel()                      # user presses Stop while step 1 runs
        return real_act(cmd, said)

    agent.act = act_then_press_stop
    say, ok, _ = agent.run("x")
    assert launched == ["notepad.exe"] and ("type_text", "never") not in ctl.calls
    assert not ok and say.endswith("Stopped.")


def test_assistant_hands_tasks_to_the_agent_and_logs_steps():
    from agent.memory import Memory

    class Planner:
        def to_command(self, text):
            return parse_command({"action": "task", "goal": "open notepad and type hi"})

    ctl, launched = FakeController(), []
    ex = Executor(ctl, Approvals(), launcher=launched.append, app_available=lambda t: True)
    memory = Memory()
    a = Assistant(ex, planner=Planner(), memory=memory, sleep=lambda s: None)
    a.agent = TaskAgent(plan=lambda g: ["open notepad", "type hi"], to_command=a.to_command, act=a.act,
                        sleep=lambda s: None)
    msgs = a.handle_text("could you open notepad and say hi in it")
    assert msgs[0]["text"] == "Done: Opening Notepad. Typed it." and launched == ["notepad.exe"]
    sources = [(e.source, e.action) for e in memory.recall("today")]
    assert ("task", "open_app") in sources and ("task", "type") in sources and ("typed", "task") in sources


def test_stop_cancels_a_running_task():
    a = Assistant(Executor(FakeController(), Approvals()))
    cancelled = []

    class Agent:
        def cancel(self):
            cancelled.append(1)

    a.agent = Agent()
    a.stop()
    assert cancelled == [1]
