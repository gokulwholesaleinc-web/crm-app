"""Regression guard for the ``proposals.quote_id → quotes.id`` FK.

The Quotes router was unmounted 2026-05-14 (#330) but the
``Proposal.quote_id`` column kept its FK declaration for legacy
provenance. The Quote ORM has no other startup registration path, so
``src.proposals.models`` performs a side-effect import to land
``quotes`` in ``Base.metadata``. Without it, SQLAlchemy can't resolve
the FK target when building DELETE statements and every
``DELETE /api/proposals/{id}`` 500s in production with
``NoReferencedTableError`` (sibling tests don't catch it because they
explicitly import ``src.quotes.models`` for SQLite schema setup).

The regression test below runs in a clean subprocess so module-level
side-effects from sibling test files can't paper over a removed import.
"""

from __future__ import annotations

import subprocess
import sys


def test_quote_table_registers_via_proposals_models_alone() -> None:
    """Importing only ``src.proposals.models`` must register the
    ``quotes`` table in ``Base.metadata``. Run in a subprocess to
    sidestep module-cache pollution from sibling tests."""
    script = (
        "import src.proposals.models;"
        " from src.database import Base;"
        " assert 'quotes' in Base.metadata.tables,"
        " 'quotes table missing — restore side-effect import in src/proposals/models.py';"
        " print('OK')"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"subprocess failed: stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert result.stdout.strip() == "OK", result.stdout
