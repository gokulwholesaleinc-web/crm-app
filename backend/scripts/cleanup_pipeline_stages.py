"""Clean up duplicate pipeline stages in the database.

Ensures only 7 stages exist per pipeline type:
  Discovery, Proposal, Negotiation, Scoping, Stalling, Won, Lost

For each (name, pipeline_type) pair:
  - Keeps the stage with the lowest ID
  - Remaps opportunities/leads from duplicates to the kept stage
  - Deletes all duplicate stages
  - Removes any stages not in the canonical 7

Usage: docker compose exec backend python scripts/cleanup_pipeline_stages.py
  Or:  python scripts/cleanup_pipeline_stages.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio

from sqlalchemy import text

from src.database import engine

CANONICAL_STAGES = {"Discovery", "Proposal", "Negotiation", "Scoping", "Stalling", "Won", "Lost"}

# Map any old stage names to canonical names
OLD_TO_CANONICAL = {
    "prospecting": "Discovery",
    "qualification": "Discovery",
    "needs analysis": "Negotiation",
    "needs_analysis": "Negotiation",
    "closed won": "Won",
    "closed_won": "Won",
    "closed lost": "Lost",
    "closed_lost": "Lost",
    "new": "Discovery",
    "contacted": "Discovery",
    "engaged": "Proposal",
    "qualified": "Proposal",
    "converted": "Won",
    "disqualified": "Lost",
    "nurturing": "Stalling",
}

STAGE_CONFIG = {
    "Discovery":    {"order": 1, "color": "#06b6d4", "probability": 10, "is_won": False, "is_lost": False},
    "Proposal":     {"order": 2, "color": "#818cf8", "probability": 30, "is_won": False, "is_lost": False},
    "Negotiation":  {"order": 3, "color": "#f59e0b", "probability": 50, "is_won": False, "is_lost": False},
    "Scoping":      {"order": 4, "color": "#10b981", "probability": 70, "is_won": False, "is_lost": False},
    "Stalling":     {"order": 5, "color": "#ef4444", "probability": 20, "is_won": False, "is_lost": False},
    "Won":          {"order": 6, "color": "#22c55e", "probability": 100, "is_won": True,  "is_lost": False},
    "Lost":         {"order": 7, "color": "#6b7280", "probability": 0,   "is_won": False, "is_lost": True},
}


async def main():
    print("=== Pipeline Stage Cleanup ===\n")

    async with engine.begin() as conn:
        # 1. Fetch all existing stages
        result = await conn.execute(text(
            "SELECT id, name, pipeline_type, is_active FROM pipeline_stages ORDER BY pipeline_type, id"
        ))
        all_stages = result.fetchall()
        print(f"Found {len(all_stages)} total stages in DB:")
        for s in all_stages:
            print(f"  id={s[0]:3d}  [{s[2]:12s}]  {s[1]:20s}  active={s[3]}")

        for ptype in ("opportunity", "lead"):
            print(f"\n--- Processing {ptype} stages ---")
            stages_for_type = [s for s in all_stages if s[2] == ptype]

            # Build map: canonical_name -> lowest ID stage
            canonical_ids = {}  # name -> id to keep
            remap = {}  # old_id -> new_id

            for s in stages_for_type:
                stage_id, stage_name = s[0], s[1]
                # Determine canonical name
                canonical = OLD_TO_CANONICAL.get(stage_name.lower(), stage_name)
                if canonical not in CANONICAL_STAGES:
                    # Try title case
                    canonical = OLD_TO_CANONICAL.get(stage_name.lower())
                    if not canonical:
                        print(f"  WARNING: Unknown stage '{stage_name}' (id={stage_id}), mapping to Discovery")
                        canonical = "Discovery"

                if canonical not in canonical_ids:
                    canonical_ids[canonical] = stage_id
                else:
                    # This is a duplicate — remap to the kept one
                    remap[stage_id] = canonical_ids[canonical]

            print(f"  Canonical stages: {canonical_ids}")
            if remap:
                print(f"  Duplicates to remap: {remap}")

            # 2. Remap opportunities/leads from duplicate stage IDs
            ref_table = "opportunities" if ptype == "opportunity" else "leads"
            for old_id, new_id in remap.items():
                result = await conn.execute(text(
                    f"UPDATE {ref_table} SET pipeline_stage_id = :new_id WHERE pipeline_stage_id = :old_id"
                ), {"new_id": new_id, "old_id": old_id})
                if result.rowcount > 0:
                    print(f"  Remapped {result.rowcount} {ref_table} from stage {old_id} -> {new_id}")

            # Also remap any stages not in canonical set (old names)
            non_canonical = [s for s in stages_for_type if s[0] not in canonical_ids.values()]
            for s in non_canonical:
                old_id = s[0]
                if old_id not in remap:
                    canonical = OLD_TO_CANONICAL.get(s[1].lower(), "Discovery")
                    new_id = canonical_ids.get(canonical)
                    if new_id and new_id != old_id:
                        result = await conn.execute(text(
                            f"UPDATE {ref_table} SET pipeline_stage_id = :new_id WHERE pipeline_stage_id = :old_id"
                        ), {"new_id": new_id, "old_id": old_id})
                        if result.rowcount > 0:
                            print(f"  Remapped {result.rowcount} {ref_table} from old stage '{s[1]}' ({old_id}) -> {new_id}")
                        remap[old_id] = new_id

            # 3. Delete duplicate/old stages
            ids_to_delete = list(remap.keys())
            if ids_to_delete:
                placeholders = ", ".join(str(i) for i in ids_to_delete)
                await conn.execute(text(
                    f"DELETE FROM pipeline_stages WHERE id IN ({placeholders})"
                ))
                print(f"  Deleted {len(ids_to_delete)} duplicate/old stages")

            # 4. Ensure any missing canonical stages exist
            for name, config in STAGE_CONFIG.items():
                if name not in canonical_ids:
                    print(f"  Creating missing stage: {name} ({ptype})")
                    await conn.execute(text(
                        "INSERT INTO pipeline_stages "
                        "(name, \"order\", color, probability, is_won, is_lost, pipeline_type, is_active) "
                        "VALUES (:name, :order, :color, :probability, :is_won, :is_lost, :ptype, true)"
                    ), {**config, "name": name, "ptype": ptype})

            # 5. Normalize remaining stages (update name, order, color, etc.)
            for name, config in STAGE_CONFIG.items():
                stage_id = canonical_ids.get(name)
                if stage_id:
                    await conn.execute(text(
                        "UPDATE pipeline_stages SET "
                        "name = :name, \"order\" = :order, color = :color, probability = :probability, "
                        "is_won = :is_won, is_lost = :is_lost, is_active = true "
                        "WHERE id = :id"
                    ), {**config, "name": name, "id": stage_id})

        # Final check
        result = await conn.execute(text(
            "SELECT id, name, pipeline_type FROM pipeline_stages WHERE is_active = true ORDER BY pipeline_type, \"order\""
        ))
        final = result.fetchall()
        print(f"\n=== Final State: {len(final)} active stages ===")
        for s in final:
            print(f"  id={s[0]:3d}  [{s[2]:12s}]  {s[1]}")

    await engine.dispose()
    print("\nCleanup complete!")


if __name__ == "__main__":
    asyncio.run(main())
