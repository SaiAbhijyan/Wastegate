"""Cloudflare-fronted APIs (seen: api.groq.com, error 1010) reject urllib's default User-Agent."""
import io
import json

from wastegate import __version__
from wastegate.providers import http


def test_post_json_sends_explicit_user_agent(monkeypatch):
    seen = {}

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout):
        seen["ua"] = req.get_header("User-agent")
        seen["ct"] = req.get_header("Content-type")
        return Resp(json.dumps({"ok": True}).encode())

    monkeypatch.setattr(http.urllib.request, "urlopen", fake_urlopen)
    assert http.post_json("https://example.invalid/x", {"Authorization": "Bearer k"}, {"a": 1}) == {"ok": True}
    assert seen["ua"] == f"wastegate/{__version__}" and seen["ct"] == "application/json"
