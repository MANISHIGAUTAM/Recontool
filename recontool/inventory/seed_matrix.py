"""Seed the persisted tool registry (ToolRow) from the full catalog.

Idempotent: re-running upserts every row (insert new, update changed) so the DB
matrix always reflects the catalog. Nothing is eliminated — web-only and
no-integration tools are seeded with their flags so the UI can still surface them.

Run:  python -m recontool.inventory.seed_matrix
"""
from __future__ import annotations

from sqlalchemy import select

from recontool.core.db import create_all, session_scope
from recontool.engine.models import ToolRow
from recontool.inventory.catalog import load_all_tools


def seed() -> dict[str, int]:
    create_all()
    inserted = updated = 0
    recs = load_all_tools()
    with session_scope() as s:
        existing = {r.slug: r for r in s.execute(select(ToolRow)).scalars()}
        for rec in recs:
            row = existing.get(rec.slug)
            fields = dict(
                name=rec.name, category=rec.category,
                classification=rec.classification, integration=rec.integration,
                consumes=rec.consumes, produces=rec.produces,
                runnable=rec.runnable, web_only=rec.web_only,
                default_on=rec.default_on, source=rec.source, modes=rec.modes,
            )
            if row is None:
                s.add(ToolRow(slug=rec.slug, **fields))
                inserted += 1
            else:
                changed = any(getattr(row, k) != v for k, v in fields.items())
                if changed:
                    for k, v in fields.items():
                        setattr(row, k, v)
                    updated += 1
    return {"total": len(recs), "inserted": inserted, "updated": updated}


if __name__ == "__main__":
    stats = seed()
    print(f"seeded tool_row: total={stats['total']} "
          f"inserted={stats['inserted']} updated={stats['updated']}")
