"""Proposals module.

Importing the view-ledger helpers here so SQLAlchemy registers the
public proposal document view tables on ``Base.metadata``. Without this,
test fixtures that call ``Base.metadata.create_all`` before any router
is loaded miss the tables and the read-before-sign queries 500.
"""

from src.proposals import attachment_views  # noqa: F401
