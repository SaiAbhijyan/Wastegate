"""Live loop speaks OpenAI function tools (Groq): declared tools, native tool_calls, invented names. No sockets."""
import json
import shutil

import pytest

from wastegate.agent import build_system, native_action, run_agent
from wastegate.catalog import load_catalog, mock_catalog
from wastegate.pipeline import plan_turn
from wastegate.providers.http import ProviderHTTPError
from wastegate.providers.live import live_catalog, live_providers
from wastegate.providers.mock import mock_providers
from wastegate.router import RouterConfig
from wastegate.skills.registry import load_builtin
from wastegate.systemone.agent_gate import agent_catalog, agent_plan
from wastegate.systemone.heuristic import HeuristicSystemOne

from conftest import FIXTURES

PROMPT = "fix the off-by-one in sliding_windows"
OLD = "    return [xs[i:i + k] for i in range(len(xs) - k)]\n"
FIX = f"<<<REPLACE windows/__init__.py\n{OLD}<<<WITH\n    return [xs[i:i + k] for i in range(len(xs) - k + 1)]\n<<<END\n"
FIVE = {"read", "grep", "edit", "pytest", "shell"}


@pytest.fixture
def obo(tmp_path):
    dst = tmp_path / "off_by_one"
    shutil.copytree(FIXTURES / "off_by_one", dst)
    return dst


def call(name, args, cid="c1"):
    return {"id": cid, "type": "function",
            "function": {"name": name, "arguments": args if isinstance(args, str) else json.dumps(args)}}


def msg(content=None, tool_calls=None):
    m = {"role": "assistant", "content": content}
    if tool_calls:
        m["tool_calls"] = tool_calls
    return {"choices": [{"message": m}], "usage": {"prompt_tokens": 10, "completion_tokens": 5}}


def run_live(obo, monkeypatch, replies):
    """replies: list of response dicts or exceptions, one per request."""
    monkeypatch.setenv("GROQ_API_KEY", "gk-fake-key-000111")
    cat = agent_catalog(live_catalog(load_catalog()))
    sent = []

    def transport(url, headers, body):
        sent.append(json.loads(json.dumps(body)))  # snapshot: messages list is mutated later
        r = replies[len(sent) - 1]
        if isinstance(r, Exception):
            raise r
        return r
    s1 = HeuristicSystemOne()
    plan = plan_turn(PROMPT, s1, cat, RouterConfig(), load_builtin())
    ap = agent_plan(PROMPT, s1, cat, RouterConfig(), gate=plan.gate)
    ap.max_steps = len(replies)
    system = build_system(plan.composed.system, ap, obo)
    res = run_agent(PROMPT, obo, ap, live_providers(cat, True, transport=transport), system, 32_000, tier="cheap")
    return res, sent


def test_outgoing_json_declares_five_function_tools(obo, monkeypatch):
    _, sent = run_live(obo, monkeypatch, [msg("<<<DONE\nnothing\n>>>")])
    tools = sent[0]["tools"]
    assert {t["function"]["name"] for t in tools} == FIVE
    assert all(t["type"] == "function" for t in tools) and sent[0]["tool_choice"] == "auto"
    assert "repo_browser" not in json.dumps(sent[0])
    grep = next(t for t in tools if t["function"]["name"] == "grep")["function"]["parameters"]
    assert grep["required"] == ["pattern"] and "path" in grep["properties"]


def test_native_grep_call_runs_and_replies_with_tool_message(obo, monkeypatch):
    res, sent = run_live(obo, monkeypatch, [msg(tool_calls=[call("grep", '{"pattern":"range"}', "call_7")]),
                                            msg("<<<DONE\nlooked\n>>>")])
    assert res.tool_calls[0]["tool"] == "grep" and res.tool_calls[0]["via"] == "native"
    m = sent[1]["messages"]
    assert m[-2]["role"] == "assistant" and m[-2]["tool_calls"][0]["id"] == "call_7"
    assert m[-1]["role"] == "tool" and m[-1]["tool_call_id"] == "call_7"
    assert "windows/__init__.py" in m[-1]["content"] and "range(len(xs) - k)" in m[-1]["content"]


def test_native_loop_reaches_pass_on_copy(obo, monkeypatch):
    res, _ = run_live(obo, monkeypatch, [msg(tool_calls=[call("grep", {"pattern": "range", "path": "windows"})]),
                                         msg(tool_calls=[call("edit", {"text": FIX}, "c2")]),
                                         msg(tool_calls=[call("pytest", {}, "c3")]),
                                         msg("<<<DONE\nfixed, tests pass\n>>>")])
    assert res.verification["status"] == "PASS", res.step_lines
    assert "k + 1" in (obo / "windows/__init__.py").read_text(encoding="utf-8")
    assert OLD in (FIXTURES / "off_by_one/windows/__init__.py").read_text(encoding="utf-8")


def test_invented_names_map_or_error_and_loop_continues(obo, monkeypatch):
    res, sent = run_live(obo, monkeypatch, [msg(tool_calls=[call("repo_browser.search", {"query": "range"})]),
                                            msg(tool_calls=[call("browser.open", {"url": "x"}, "c2")]),
                                            msg("<<<DONE\nok\n>>>")])
    assert [c["tool"] for c in res.tool_calls[:2]] == ["grep", "browser.open"]
    assert res.tool_calls[1]["ok"] is False and "unknown tool" in res.tool_calls[1]["error"]
    assert "unknown tool" in sent[2]["messages"][-1]["content"] and res.stop_reason == "done"
    assert all(t["function"]["name"] in FIVE for b in sent for t in b["tools"])


def test_only_first_of_parallel_calls_executes(obo, monkeypatch):
    _, sent = run_live(obo, monkeypatch, [msg(tool_calls=[call("grep", {"pattern": "range"}, "a"),
                                                          call("read", {"path": "windows/__init__.py"}, "b")]),
                                          msg("<<<DONE\nok\n>>>")])
    tail = sent[1]["messages"][-2:]
    assert [t["tool_call_id"] for t in tail] == ["a", "b"] and "not executed" in tail[1]["content"]


def test_groq_tool_use_failed_400_is_recovered(obo, monkeypatch):
    body = json.dumps({"error": {"message": "Tool choice is none, but model called a tool",
                                 "type": "invalid_request_error", "code": "tool_use_failed",
                                 "failed_generation": json.dumps({"name": "repo_browser.grep",
                                                                  "arguments": {"path": "windows",
                                                                                "query": "sliding_windows"}})}})
    res, sent = run_live(obo, monkeypatch, [ProviderHTTPError(400, body), msg("<<<DONE\nok\n>>>")])
    assert res.provider_error is None and res.stop_reason == "done"
    assert res.tool_calls[0]["tool"] == "grep" and res.tool_calls[0]["via"] == "recovered"
    assert "def sliding_windows" in sent[1]["messages"][-1]["content"]


def test_unrecoverable_400_still_stops(obo, monkeypatch):
    res, _ = run_live(obo, monkeypatch, [ProviderHTTPError(400, '{"error":{"message":"max_tokens too large"}}'),
                                         msg("<<<DONE\nnever\n>>>")])
    assert res.stop_reason == "provider error" and res.provider_error["status"] == 400


def test_native_action_mapping():
    assert native_action("repo_browser.grep", '{"query":"x","path":"a"}') == ("grep", "x\na", None)
    assert native_action("functions/read", '{"path":"a.py"}') == ("read", "a.py", None)
    assert native_action("search_files", '{"pattern":"y"}') == ("grep", "y", None)
    assert native_action("shell", '{"cmd":"git diff"}') == ("shell", "git diff", None)
    assert native_action("pytest", "") == ("pytest", "", None)
    assert native_action("open_url", "{}")[2].startswith("unknown tool")
    assert "bad arguments" in native_action("grep", "{not json")[2]


def test_mock_sends_no_tools_and_text_protocol_passes(obo, tmp_path):
    cat = mock_catalog()
    s1 = HeuristicSystemOne()
    plan = plan_turn(PROMPT, s1, cat, RouterConfig(), load_builtin())
    ap = agent_plan(PROMPT, s1, cat, RouterConfig(), gate=plan.gate)
    system = build_system(plan.composed.system, ap, obo)
    res = run_agent(PROMPT, obo, ap, mock_providers(FIXTURES / "replies/agent_obo"), system, 4000, tier="cheap")
    assert res.verification["status"] == "PASS" and all(c["via"] == "text" for c in res.tool_calls)
