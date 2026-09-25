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


def test_report_has_host_header_and_redaction_line(tmp_path, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk-smoke-planted-2468")
    rec = {**REC, "prompt": "p gsk-smoke-planted-2468",
           "calls": [{**REC["calls"][0], "provider": "groq", "model_id": "openai/gpt-oss-120b"}]}
    text = write_smoke_report(rec, tmp_path, "20260925").read_text()
    assert "wiring + contract check, not a benchmark" in text
    assert "host: api.groq.com" in text and "`openai/gpt-oss-120b`" in text
    assert "redaction check: no configured key value present: yes" in text
    assert "gsk-smoke-planted-2468" not in text


def test_report_contract_lines(tmp_path):
    rec = {**REC, "test_file_changed": True,
           "tester": {"status": "skipped", "parse_error": "no TESTER: line in reply"},
           "skeptic": {"verdict": "approve", "parse_error": None}}
    text = write_smoke_report(rec, tmp_path, "20260925").read_text()
    assert "- test file changed: yes" in text
    assert "- tester parsed: no (skipped: no TESTER: line in reply)" in text
    assert "- skeptic parsed: yes (approve)" in text


def test_report_not_routed_is_na(tmp_path):
    rec = {**REC, "tester": {"status": "not routed", "findings": [], "reason": ""}, "skeptic": None}
    text = write_smoke_report(rec, tmp_path, "20260925").read_text()
    assert "- tester parsed: n/a (not routed)" in text and "- skeptic parsed: n/a (not routed)" in text


def test_report_loop_lines(tmp_path):
    rec = {**REC, "followup": {"ran": True, "reason": "", "edits": ["tests/test_x.py"]},
           "mid_escalation": {"ran": False, "reason": "nothing unresolved"},
           "skeptic": {"verdict": "reject", "effective": "dismissed", "parse_error": None,
                       "dropped": [{"finding": "a", "reason": "no file path"}]}}
    text = write_smoke_report(rec, tmp_path, "20260925").read_text()
    assert "- follow-up ran: yes (edits: tests/test_x.py)" in text
    assert "- mid escalation ran: no (nothing unresolved)" in text
    assert "- skeptic parsed: yes (reject -> dismissed; 1 finding(s) dropped)" in text
