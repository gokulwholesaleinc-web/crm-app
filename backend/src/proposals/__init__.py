"""Proposals module.

Importing the attachment-views model here so SQLAlchemy registers the
``proposal_attachment_views`` table on ``Base.metadata``. Without this,
test fixtures that call ``Base.metadata.create_all`` before any router
is loaded miss the table and the read-before-sign queries 500.
"""

from src.proposals import attachment_views  # noqa: F401
