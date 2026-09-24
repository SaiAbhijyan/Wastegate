import json

import pytest

from wastegate.log import TurnLogger, redact


@pytest.mark.parametrize("secret", [
    "sk-ant-api03-AbCdEfGhIjKlMnOpQrStUvWx",
    "sk-proj-AbCdEfGhIjKlMnOpQrStUvWx1234",
    "ghp_AbCdEfGhIjKlMnOpQrStUvWx123456",
    "Bearer abc.def.ghi-jkl",
])
def test_redact_patterns(secret):
    out = redact(f"key is {secret} ok")
    assert secret not in out and "ok" in out


@pytest.mark.parametrize("var", ["JEV_API_KEY", "TYPESAFE_API_KEY"])
def test_logger_redacts_env_key_values(tmp_path, monkeypatch, var):
    monkeypatch.setenv(var, "plainvalue-no-pattern-777")
    lg = TurnLogger(tmp_path)
    lg.write({"prompt": "my key plainvalue-no-pattern-777 leaked", "nested": {"k": "sk-ant-XXXXXXXXXXXXXXXXXXXX"}})
    raw = (tmp_path / "turns.jsonl").read_text()
    assert "plainvalue-no-pattern-777" not in raw
    assert "sk-ant-XXXXXXXXXXXXXXXXXXXX" not in raw
    rec = json.loads(raw.splitlines()[0])
    assert rec["tokens"] is None and rec["usd"] is None and "ts" in rec and "turn_id" in rec
