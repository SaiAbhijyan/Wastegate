"""Static scan for imported skills. Imported SKILL.md is untrusted prose.

Rules are regex heuristics (SkillSpector-class *checks*, not that tool). They catch obvious
injection / exfil / tool-poisoning / scripts / size abuse. Purpose-mismatch detection needs a
model and is NOT implemented. A clean scan does not make a skill safe; imports stay quarantined
until a human allows them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

MAX_SKILL_BYTES = 15_000
SCRIPT_EXT = {".sh", ".bash", ".zsh", ".py", ".js", ".ts", ".ps1", ".bat", ".cmd", ".exe", ".bin", ".so", ".dll"}

TEXT_RULES: list[tuple[str, str, str]] = [
    ("injection", "high", r"\b(ignore|disregard|forget)\s+(all\s+)?(the\s+)?(previous|prior|above|earlier|system)\s+(instructions|prompts?|rules)"),
    ("injection", "high", r"\bdo not (tell|inform|mention to|alert) the user\b"),
    ("injection", "high", r"\b(you are now|new system prompt|override (your|the) (instructions|rules))\b"),
    ("exfil", "high", r"\b(send|post|upload|exfiltrat\w*|forward|transmit)\b.{0,80}\b(api[_ ]?keys?|tokens?|secrets?|credentials?|passwords?|env(ironment)? var\w*)\b"),
    ("secrets-access", "high", r"(~/\.ssh|id_rsa|id_ed25519|\.aws/credentials|aws_secret|/etc/passwd|\.env\b|\.netrc)"),
    ("tool-poisoning", "high", r"\b(curl|wget)\b[^\n|]*\|\s*(sh|bash|zsh|python)"),
    ("tool-poisoning", "high", r"\b(always|first|silently) (run|execute|call)\b"),
    ("tool-poisoning", "high", r"rm\s+-rf\s+[/~]|chmod\s+\+x|\beval\s*\(|base64\s+(-d|--decode)"),
    ("blob", "medium", r"[A-Za-z0-9+/=]{200,}"),
    ("url", "info", r"https?://[^\s)>\]]+"),
]


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str
    detail: str


@dataclass(frozen=True)
class ScanReport:
    findings: tuple[Finding, ...]
    quarantine: bool = True  # imports always start quarantined

    @property
    def high(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "high"]


def scan_text(text: str) -> list[Finding]:
    out = []
    for rule, sev, pat in TEXT_RULES:
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            out.append(Finding(rule, sev, m.group(0)[:120]))
    return out


def _user_supplied_builtin(d: Path) -> bool:
    """Size exemption only for shipped builtins with provenance text 'user-supplied'; imports cannot self-exempt."""
    from .registry import _sidecar_provenance, builtin_root
    try:
        inside = d.resolve().is_relative_to(builtin_root().resolve())
    except OSError:
        return False
    return inside and _sidecar_provenance(d).get("text") == "user-supplied"


def scan_skill_dir(d: Path) -> ScanReport:
    d = Path(d)
    findings: list[Finding] = []
    skill = d / "SKILL.md"
    if not skill.exists():
        findings.append(Finding("missing", "high", "no SKILL.md"))
    else:
        size = skill.stat().st_size
        if size > MAX_SKILL_BYTES:
            if _user_supplied_builtin(d):
                findings.append(Finding("size", "info", f"{size} bytes > {MAX_SKILL_BYTES}: exempt (user-supplied builtin)"))
            else:
                findings.append(Finding("size", "high", f"{size} bytes > {MAX_SKILL_BYTES}"))
        findings += scan_text(skill.read_text(errors="replace", encoding="utf-8"))
    for f in sorted(d.rglob("*")):
        if f.is_file() and f.name != "SKILL.md":
            if f.suffix.lower() in SCRIPT_EXT or f.stat().st_mode & 0o111:
                findings.append(Finding("script", "high", str(f.relative_to(d))))
            elif f.suffix.lower() in {".md", ".txt"}:
                findings += scan_text(f.read_text(errors="replace", encoding="utf-8"))
    return ScanReport(tuple(findings))
