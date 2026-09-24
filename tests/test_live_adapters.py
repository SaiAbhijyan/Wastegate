"""Live adapters stay dark: no key or no --live -> LiveDisabled; never a socket in tests."""
import pytest
from typer.testing import CliRunner

from wastegate.cli import app
from wastegate.providers.base import LiveDisabled
from wastegate.providers.anthropic import AnthropicProvider
from wastegate.providers.openai import OpenAIProvider
from wastegate.providers.openrouter import OpenRouterProvider

ADAPTERS = [(AnthropicProvider, "ANTHROPIC_API_KEY"), (OpenAIProvider, "OPENAI_API_KEY"),
            (OpenRouterProvider, "OPENROUTER_API_KEY")]
MSGS = [{"role": "user", "content": "hi"}]


@pytest.mark.parametrize("cls,var", ADAPTERS)
def test_no_key_raises(cls, var):
    with pytest.raises(LiveDisabled, match="no key or --live not set"):
        cls(allow_network=True).complete("m", "sys", MSGS, 10)


@pytest.mark.parametrize("cls,var", ADAPTERS)
def test_key_without_live_raises(cls, var, monkeypatch):
    monkeypatch.setenv(var, "k-123456")
    with pytest.raises(LiveDisabled, match="no key or --live not set"):
        cls().complete("m", "sys", MSGS, 10)


@pytest.mark.parametrize("cls,var", ADAPTERS)
def test_key_and_live_still_dark_under_pytest(cls, var, monkeypatch):
    monkeypatch.setenv(var, "k-123456")
    with pytest.raises(LiveDisabled):
        cls(allow_network=True).complete("m", "sys", MSGS, 10)


@pytest.mark.parametrize("cls,var", ADAPTERS)
def test_repr_hides_key(cls, var, monkeypatch):
    monkeypatch.setenv(var, "k-supersecret-9")
    assert "supersecret" not in repr(cls(allow_network=True))


def _fake(response, seen):
    def transport(url, headers, body):
        seen.update(url=url, headers=headers, body=body)
        return response
    return transport


def test_anthropic_request_and_usage(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k-anth")
    seen = {}
    resp = {"content": [{"type": "text", "text": "hello"}, {"type": "tool_use", "id": "x"}],
            "usage": {"input_tokens": 10, "cache_creation_input_tokens": 5,
                      "cache_read_input_tokens": None, "output_tokens": 7}}
    c = AnthropicProvider(allow_network=True, transport=_fake(resp, seen)).complete("m1", "sys", MSGS, 64)
    assert seen["url"] == "https://api.anthropic.com/v1/messages"
    assert seen["headers"]["x-api-key"] == "k-anth" and seen["headers"]["anthropic-version"] == "2023-06-01"
    assert seen["body"] == {"model": "m1", "max_tokens": 64, "system": "sys", "messages": MSGS}
    assert c.text == "hello" and c.provider == "anthropic" and c.model_id == "m1"
    assert (c.usage.input_tokens, c.usage.output_tokens) == (15, 7)  # input + cache_creation + cache_read


@pytest.mark.parametrize("cls,var,url", [
    (OpenAIProvider, "OPENAI_API_KEY", "https://api.openai.com/v1/chat/completions"),
    (OpenRouterProvider, "OPENROUTER_API_KEY", "https://openrouter.ai/api/v1/chat/completions"),
])
def test_openai_compatible_request_and_usage(cls, var, url, monkeypatch):
    monkeypatch.setenv(var, "k-oai")
    seen = {}
    resp = {"choices": [{"message": {"role": "assistant", "content": "yo"}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7, "cost": 0.01}}
    c = cls(allow_network=True, transport=_fake(resp, seen)).complete("m2", "sys", MSGS, 32)
    assert seen["url"] == url and seen["headers"]["Authorization"] == "Bearer k-oai"
    assert seen["body"]["messages"][0] == {"role": "system", "content": "sys"}
    assert c.text == "yo" and (c.usage.input_tokens, c.usage.output_tokens) == (3, 4)


@pytest.mark.parametrize("cls,var", ADAPTERS)
def test_missing_usage_is_none_not_estimated(cls, var, monkeypatch):
    monkeypatch.setenv(var, "k")
    resp = {"content": [{"type": "text", "text": "a b c"}],
            "choices": [{"message": {"content": "a b c"}}]}
    c = cls(allow_network=True, transport=lambda *a: resp).complete("m", "s", MSGS, 8)
    assert c.usage is None


def test_socket_guard_active():
    import socket
    with pytest.raises(RuntimeError, match="network disabled"):
        socket.create_connection(("example.com", 443))


def test_cli_live_without_key_exits_2(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = CliRunner().invoke(app, ["ask", "--live", "fix the bug in tiny_pkg and add a regression test"])
    assert r.exit_code == 2 and "no key or --live not set" in r.output
    assert not (tmp_path / ".wastegate").exists()  # nothing logged, nothing written


def test_cli_modes_exclusive():
    r = CliRunner().invoke(app, ["ask", "--live", "--dry-run", "x"])
    assert r.exit_code == 2
