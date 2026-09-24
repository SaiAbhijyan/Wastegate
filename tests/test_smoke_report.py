from wastegate.smoke import write_smoke_report

REC = {"prompt": "p", "mode": "live", "tests": {"before": 1, "after": 0},
       "calls": [{"role": "driver", "tier": "mid", "provider": "openai", "model_id": "gpt-5.6-terra",
                  "tokens_in": 11, "tokens_out": 2, "usd": None,
                  "usage_raw": {"prompt_tokens": 11, "completion_tokens": 2, "note": "sk-proj-AAAAAAAAAAAAAAAAAAAAAAAA"}}]}


def test_report_has_raw_usage_redacted_and_null_usd(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "plain-key-value-123")
    rec = {**REC, "prompt": "leak plain-key-value-123"}
    p = write_smoke_report(rec, tmp_path, "20260924")
    assert p.name == "20260924-live-smoke.md"
    text = p.read_text()
    assert '"prompt_tokens": 11' in text and '"completion_tokens": 2' in text
    assert "usd: null" in text and "not a benchmark" in text
    assert "plain-key-value-123" not in text and "sk-proj-AAAA" not in text


def test_report_never_overwrites(tmp_path):
    a = write_smoke_report(REC, tmp_path, "20260924")
    b = write_smoke_report(REC, tmp_path, "20260924")
    assert a != b and b.name == "20260924-live-smoke-2.md" and a.exists()
