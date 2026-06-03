"""HTTP error-mapping context managers for the onboarding router.

Extracted from ``router.py`` (build-order §C) to keep the route module under
the per-file budget while preserving the precise status mapping the build
order mandates (§G #2): service errors must NOT collapse to a blanket 400.

  * FieldDefinitionError      → 422 (geometry / bounds / esign↔sig)
  * Stale/RetiredTemplateError → 409 (edit conflict)
  * PdfRejectedError (ValueError) → 400 (via ``value_error_as_400``)
  * StorageWriteError         → 503 (R2 / disk write outage)
"""

import logging
from contextlib import contextmanager

from fastapi import HTTPException

from src.core.constants import HTTPStatus
from src.core.http_errors import value_error_as_400
from src.onboarding.packet_errors import (
    PacketGoneError,
    PacketInfraError,
    PacketNotFoundError,
    PacketRaceError,
    PacketValidationError,
)
from src.onboarding.service import (
    DuplicateTemplateNameError,
    FieldDefinitionError,
    RetiredTemplateError,
    StaleTemplateError,
    StorageWriteError,
)

logger = logging.getLogger(__name__)


@contextmanager
def field_definition_error_as_422():
    """FieldDefinitionError → 422 (geometry/bounds/esign); Stale/Retired → 409.

    Also maps ``DuplicateTemplateNameError`` → 422 — a template-save concern
    (the unique-name backstop, S1) that belongs on the same template write path.
    """
    try:
        yield
    except (FieldDefinitionError, DuplicateTemplateNameError) as exc:
        logger.warning("Onboarding template-save validation 422: %s", exc)
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except (StaleTemplateError, RetiredTemplateError) as exc:
        logger.warning("Onboarding edit conflict 409: %s", exc)
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT, detail=str(exc)
        ) from exc


@contextmanager
def upload_errors_mapped():
    """Map service-raised upload errors: PdfRejectedError (ValueError) → 400,
    RetiredTemplateError → 409 (#11), StorageWriteError → 503 (R2 outage)."""
    try:
        with value_error_as_400():
            yield
    except RetiredTemplateError as exc:
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT, detail=str(exc)
        ) from exc
    except StorageWriteError as exc:
        logger.warning("Onboarding PDF storage write failed (503): %s", exc)
        raise HTTPException(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc


@contextmanager
def packet_errors_mapped():
    """Map Phase-2 packet errors to HTTP status (NOT a blanket 400).

    race/version/wrong-status → 409, validation/overflow → 422, infra/storage
    → 503, token-not-found/expired → 404, terminal-dead → 410. Each source
    exception is a non-ValueError class so the status can't be downgraded.
    """
    try:
        yield
    except PacketRaceError as exc:
        logger.info("Onboarding packet conflict 409: %s", exc)
        raise HTTPException(
            status_code=HTTPStatus.CONFLICT, detail=str(exc)
        ) from exc
    except PacketValidationError as exc:
        logger.info("Onboarding packet validation 422: %s", exc)
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except PacketGoneError as exc:
        logger.info("Onboarding packet gone 410: %s", exc)
        raise HTTPException(
            status_code=HTTPStatus.GONE, detail=str(exc)
        ) from exc
    except PacketNotFoundError as exc:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail=str(exc)
        ) from exc
    except PacketInfraError as exc:
        logger.warning("Onboarding packet infra failure 503: %s", exc)
        raise HTTPException(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc


# Alias: completion uses the same mapping (race→409, validation→422, infra→503).
complete_errors_mapped = packet_errors_mapped
