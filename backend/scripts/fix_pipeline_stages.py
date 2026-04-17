"""Fix pipeline stages for existing databases.

Ensures lead pipeline stages exist and maps leads with NULL pipeline_stage_id
to the correct stage based on their status field.

Usage: docker compose exec backend python scripts/fix_pipeline_stages.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio

from sqlalchemy import text

from src.database import engine

LEAD_STAGES = [
    {"name": "Discovery",    "order": 1, "color": "#06b6d4", "probability": 10, "is_won": False, "is_lost": False},
    {"name": "Proposal",     "order": 2, "color": "#818cf8", "probability": 30, "is_won": False, "is_lost": False},
    {"name": "Negotiation",  "order": 3, "color": "#f59e0b", "probability": 50, "is_won": False, "is_lost": False},
    {"name": "Scoping",      "order": 4, "color": "#10b981", "probability": 70, "is_won": False, "is_lost": False},
    {"name": "Stalling",     "order": 5, "color": "#ef4444", "probability": 20, "is_won": False, "is_lost": False},
    {"name": "Won",          "order": 6, "color": "#22c55e", "probability": 100, "is_won": True, "is_lost": False},
    {"name": "Lost",         "order": 7, "color": "#6b7280", "probability": 0, "is_won": False, "is_lost": True},
]

STATUS_TO_STAGE = {
    "new": "Discovery",
    "contacted": "Discovery",
    "qualified": "Proposal",
    "negotiation": "Negotiation",
    "converted": "Won",
    "lost": "Lost",
}


async def main():
    print("Fixing pipeline stages...")
    summary = []

    async with engine.begin() as conn:
        # 1. Fix NULL pipeline_type on existing stages
        result = await conn.execute(text(
            "UPDATE pipeline_stages SET pipeline_type = 'opportunity' "
            "WHERE pipeline_type IS NULL"
        ))
        if result.rowcount > 0:
            msg = f"  Updated {result.rowcount} stages with NULL pipeline_type to 'opportunity'"
            print(msg)
            summary.append(msg)
        else:
            print("  No stages with NULL pipeline_type found.")

        # 2. Check if lead pipeline stages exist
        result = await conn.execute(text(
            "SELECT COUNT(*) FROM pipeline_stages WHERE pipeline_type = 'lead'"
        ))
        lead_count = result.scalar()

        if lead_count == 0:
            print("  Inserting lead pipeline stages...")
            for stage in LEAD_STAGES:
                await conn.execute(text(
                    "INSERT INTO pipeline_stages "
                    "(name, \"order\", color, probability, is_won, is_lost, pipeline_type, is_active) "
                    "VALUES (:name, :order, :color, :probability, :is_won, :is_lost, 'lead', true)"
                ), {
                    "name": stage["name"],
                    "order": stage["order"],
                    "color": stage["color"],
                    "probability": stage["probability"],
                    "is_won": stage["is_won"],
                    "is_lost": stage["is_lost"],
                })
            msg = f"  Inserted {len(LEAD_STAGES)} lead pipeline stages"
            print(msg)
            summary.append(msg)
        else:
            print(f"  Lead pipeline stages already exist ({lead_count} found), skipping insert.")

        # 3. Update leads with NULL pipeline_stage_id based on status
        # First, build a map of lead stage name -> id
        result = await conn.execute(text(
            "SELECT id, name FROM pipeline_stages WHERE pipeline_type = 'lead'"
        ))
        stage_rows = result.fetchall()
        stage_name_to_id = {row[1]: row[0] for row in stage_rows}

        total_updated = 0
        for status, stage_name in STATUS_TO_STAGE.items():
            stage_id = stage_name_to_id.get(stage_name)
            if not stage_id:
                print(f"  WARNING: Could not find lead stage '{stage_name}', skipping status '{status}'")
                continue

            result = await conn.execute(text(
                "UPDATE leads SET pipeline_stage_id = :stage_id "
                "WHERE pipeline_stage_id IS NULL AND status = :status"
            ), {"stage_id": stage_id, "status": status})

            if result.rowcount > 0:
                msg = f"  Mapped {result.rowcount} leads with status='{status}' to stage '{stage_name}'"
                print(msg)
                summary.append(msg)
                total_updated += result.rowcount

        if total_updated == 0:
            print("  No leads with NULL pipeline_stage_id needed updating.")

    await engine.dispose()

    print("\n--- Summary ---")
    if summary:
        for line in summary:
            print(line)
    else:
        print("  No changes were needed. Database is already up to date.")
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
