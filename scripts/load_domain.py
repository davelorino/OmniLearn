#!/usr/bin/env python
"""
Load a domain’s YAML skill tree + config into Postgres.

Usage:
    python scripts/load_domain.py stats
"""
from pathlib import Path
import sys, yaml, uuid
from sqlmodel import Session
from core.db import engine
from core.models import Interest, SkillNode

def _read_yaml(path: Path):
    return yaml.safe_load(path.read_text()) if path.exists() else {}

def load(domain_slug: str, base: Path = Path("domains")):
    cfg   = _read_yaml(base / domain_slug / "config.yaml")
    nodes = _read_yaml(base / domain_slug / "skills.yaml")

    if not (cfg and nodes):
        sys.exit(f"❌  Missing YAML for domain “{domain_slug}”")

    with Session(engine) as s:
        # ── interest row ──────────────────────────────────────────────
        interest = Interest(
            slug  = domain_slug,
            title = cfg.get("name", domain_slug.title()),
            daily_time_budget           = cfg.get("daily_time_budget"),
            streak_gate_correct_in_row = cfg.get("streak_gate", {}).get("correct_in_row"),
        )
        s.add(interest)
        s.commit()      # need ID for FK

        # ── skill nodes ───────────────────────────────────────────────
        for n in nodes:
            s.add(
                SkillNode(
                    id=n["id"],
                    label=n["label"],
                    parent_id=n["parent_id"],
                    interest_id=interest.id,
                    depth=n["id"].count("/"),
                )
            )
        s.commit()
        print(f"✔  Loaded {len(nodes)} skill nodes for “{domain_slug}”")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: load_domain.py <slug>")
    load(sys.argv[1])
