"""Skill registry: Agent Skills layout (SKILL.md = YAML frontmatter + markdown body)."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

import yaml

from ..systemone.base import SKILL_IDS

# verification-harness is loaded conditionally by the agent loop; it is not a gate skill_primary option.
BUILTIN_IDS = SKILL_IDS + ("verification-harness",)


@dataclass(frozen=True)
class Skill:
    id: str
    name: str
    description: str
    provenance: dict = field(hash=False)
    quarantined: bool
    body: str
    sha256: str
    path: Path


def parse_skill(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"{path}: missing YAML frontmatter")
    _, fm, body = text.split("---\n", 2)
    meta = yaml.safe_load(fm) or {}
    if not isinstance(meta, dict) or "name" not in meta:
        raise ValueError(f"{path}: frontmatter needs a name")
    return meta, body


def _sidecar_provenance(d: Path) -> dict:
    """provenance.toml next to SKILL.md (used when SKILL.md must stay byte-exact, e.g. user-supplied text)."""
    from ..catalog import tomllib
    p = d / "provenance.toml"
    return tomllib.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def load_skill_dir(d: Path, imported: bool = False) -> Skill:
    p = Path(d) / "SKILL.md"
    meta, body = parse_skill(p)
    prov = meta.get("provenance") or _sidecar_provenance(Path(d))
    if imported:
        prov = {"upstream": prov.get("upstream", "unknown"), "sha": prov.get("sha", "unknown"),
                "license": prov.get("license", "unknown"), "text": "vendored", "scanned": "pending"}
    return Skill(
        id=Path(d).name if imported else meta["name"],
        name=meta["name"],
        description=meta.get("description", ""),
        provenance=prov,
        quarantined=True if imported else bool(meta.get("quarantined", False)),
        body=body,
        sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
        path=p,
    )


def builtin_root() -> Path:
    return Path(str(resources.files("wastegate").joinpath("skills/builtin")))


def load_builtin() -> dict[str, Skill]:
    root = builtin_root()
    return {sid: load_skill_dir(root / sid) for sid in BUILTIN_IDS}
