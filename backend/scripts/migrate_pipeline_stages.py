"""Migrate pipeline stages to the unified 7-stage pipeline.

Replaces all old opportunity and lead stages with:
  Discovery, Proposal, Negotiation, Scoping, Stalling, Won, Lost

Existing opportunities and leads are re-mapped to the closest new stage.

Usage: docker compose exec backend python scripts/migrate_pipeline_stages.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
from sqlalchemy import text
from src.database import engine


NEW_STAGES = [
    {"name": "Discovery",    "order": 1, "color": "#06b6d4", "probability": 10, "is_won": False, "is_lost": False},
    {"name": "Proposal",     "order": 2, "color": "#818cf8", "probability": 30, "is_won": False, "is_lost": False},
    {"name": "Negotiation",  "order": 3, "color": "#f59e0b", "probability": 50, "is_won": False, "is_lost": False},
    {"name": "Scoping",      "order": 4, "color": "#10b981", "probability": 70, "is_won": False, "is_lost": False},
    {"name": "Stalling",     "order": 5, "color": "#ef4444", "probability": 20, "is_won": False, "is_lost": False},
    {"name": "Won",          "order": 6, "color": "#22c55e", "probability": 100, "is_won": True,  "is_lost": False},
    {"name": "Lost",         "order": 7, "color": "#6b7280", "probability": 0,   "is_won": False, "is_lost": True},
]

# Map old stage names (lowercase) to new stage names
OLD_TO_NEW = {
    # Old opportunity stages
    "prospecting": "Discovery",
    "qualification": "Discovery",
    "proposal": "Proposal",
    "proposals on": "Proposal",
    "negotiation": "Negotiation",
    "negotiations": "Negotiation",
    "needs analysis": "Negotiation",
    "scoping": "Scoping",
    "stalling": "Stalling",
    "closed won": "Won",
    "won": "Won",
    "closed lost": "Lost",
    "lost": "Lost",
    # Old lead stages
    "new": "Discovery",
    "contacted": "Discovery",
    "engaged": "Proposal",
    "qualified": "Proposal",
    "converted": "Won",
    "disqualified": "Lost",
    "nurturing": "Stalling",
    # Direct matches (already correct)
    "discovery": "Discovery",
}


async def main():
    print("Migrating pipeline stages to unified 7-stage pipeline...")
    print(f"Target stages: {', '.join(s['name'] for s in NEW_STAGES)}\n")

    async with engine.begin() as conn:
        # 1. Get all existing stages
        result = await conn.execute(text(
            "SELECT id, name, pipeline_type FROM pipeline_stages ORDER BY pipeline_type, \"order\""
        ))
        old_stages = result.fetchall()
        print(f"Found {len(old_stages)} existing stages:")
        for s in old_stages:
            print(f"  [{s[2]}] {s[1]} (id={s[0]})")

        # 2. Insert new stages for each pipeline type
        for ptype in ("opportunity", "lead"):
            print(f"\nCreating new {ptype} stages...")
            for stage in NEW_STAGES:
                await conn.execute(text(
                    "INSERT INTO pipeline_stages "
                    "(name, \"order\", color, probability, is_won, is_lost, pipeline_type, is_active) "
                    "VALUES (:name, :order, :color, :probability, :is_won, :is_lost, :ptype, true)"
                ), {**stage, "ptype": ptype})
            print(f"  Inserted {len(NEW_STAGES)} {ptype} stages")

        # 3. Build new stage ID lookup
        result = await conn.execute(text(
            "SELECT id, name, pipeline_type FROM pipeline_stages WHERE is_active = true "
            "ORDER BY id DESC"
        ))
        all_stages = result.fetchall()
        # Use the newest stages (highest IDs) for the new names
        new_stage_ids = {}
        for s in all_stages:
            key = (s[1], s[2])  # (name, pipeline_type)
            if key not in new_stage_ids:
                new_stage_ids[key] = s[0]

        # 4. Remap opportunities
        old_opp_stages = [s for s in old_stages if s[2] == "opportunity"]
        for old_stage in old_opp_stages:
            old_id = old_stage[0]
            old_name = old_stage[1]
            new_name = OLD_TO_NEW.get(old_name.lower())
            if not new_name:
                print(f"  WARNING: No mapping for opportunity stage '{old_name}', mapping to Discovery")
                new_name = "Discovery"
            new_id = new_stage_ids.get((new_name, "opportunity"))
            if new_id and new_id != old_id:
                result = await conn.execute(text(
                    "UPDATE opportunities SET pipeline_stage_id = :new_id "
                    "WHERE pipeline_stage_id = :old_id"
                ), {"new_id": new_id, "old_id": old_id})
                if result.rowcount > 0:
                    print(f"  Remapped {result.rowcount} opportunities: '{old_name}' -> '{new_name}'")

        # 5. Remap leads
        old_lead_stages = [s for s in old_stages if s[2] == "lead"]
        for old_stage in old_lead_stages:
            old_id = old_stage[0]
            old_name = old_stage[1]
            new_name = OLD_TO_NEW.get(old_name.lower())
            if not new_name:
                print(f"  WARNING: No mapping for lead stage '{old_name}', mapping to Discovery")
                new_name = "Discovery"
            new_id = new_stage_ids.get((new_name, "lead"))
            if new_id and new_id != old_id:
                result = await conn.execute(text(
                    "UPDATE leads SET pipeline_stage_id = :new_id "
                    "WHERE pipeline_stage_id = :old_id"
                ), {"new_id": new_id, "old_id": old_id})
                if result.rowcount > 0:
                    print(f"  Remapped {result.rowcount} leads: '{old_name}' -> '{new_name}'")

        # 6. Deactivate old stages
        old_ids = [s[0] for s in old_stages]
        if old_ids:
            placeholders = ", ".join(str(i) for i in old_ids)
            await conn.execute(text(
                f"UPDATE pipeline_stages SET is_active = false WHERE id IN ({placeholders})"
            ))
            print(f"\n  Deactivated {len(old_ids)} old stages")

    await engine.dispose()
    print("\nMigration complete!")


if __name__ == "__main__":
    asyncio.run(main())
