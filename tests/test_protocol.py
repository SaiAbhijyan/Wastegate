"""Agent action protocol: block form, single-line form, markdown fences."""
import pytest

from wastegate.agent import parse_action


@pytest.mark.parametrize("text,want", [
    ("<<<TOOL read\nwindows/__init__.py\n>>>\n", ("read", "windows/__init__.py")),
    ("TOOL read windows/__init__.py\n", ("read", "windows/__init__.py")),
    ("I'll look.\nTOOL grep range\\(len\n", ("grep", "range\\(len")),
    ("TOOL pytest\n", ("pytest", "")),
    ("TOOL shell git diff\n", ("shell", "git diff")),
    ("```\n<<<TOOL read\nwindows/__init__.py\n>>>\n```\n", ("read", "windows/__init__.py")),
    ("```text\nTOOL read windows/__init__.py\n```\n", ("read", "windows/__init__.py")),
    ("```bash\nTOOL pytest\n```", ("pytest", "")),
    ("<<<DONE\nall good\n>>>\n", ("done", "all good")),
    ("```\n<<<DONE\nall good\n>>>\n```", ("done", "all good")),
    ("no action here", ("final", "no action here")),
])
def test_parse_action(text, want):
    assert parse_action(text) == want


def test_tool_edit_single_line_then_block():
    text = ("TOOL edit\n<<<REPLACE a.py\nx\n<<<WITH\ny\n<<<END\n")
    assert parse_action(text)[0] == "edit"


def test_fenced_replace_is_edit():
    text = "```\n<<<REPLACE a.py\nx\n<<<WITH\ny\n<<<END\n```\n"
    assert parse_action(text)[0] == "edit"


def test_earliest_action_wins():
    assert parse_action("TOOL pytest\n<<<DONE\nx\n>>>\n")[0] == "pytest"
    assert parse_action("<<<DONE\nx\n>>>\nTOOL pytest\n")[0] == "done"


def test_inline_mention_is_not_an_action():
    assert parse_action("You could use TOOL read later.")[0] == "final"
