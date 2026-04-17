"""HTTP error helpers for router-level exception handling.

Routers repeatedly wrap service calls with the same boilerplate:

    try:
        await service.do_something(...)
    except ValueError as exc:
        raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=str(exc))

The `value_error_as_400` context manager collapses that to:

    with value_error_as_400():
        await service.do_something(...)
"""

from contextlib import contextmanager

from fastapi import HTTPException

from src.core.constants import HTTPStatus


@contextmanager
def value_error_as_400():
    """Convert a ValueError raised inside the block to HTTP 400.

    Use around a service call that signals domain validation failures via
    ValueError. The `from exc` preserves the original traceback so the
    FastAPI error handler still logs the root cause.
    """
    try:
        yield
    except ValueError as exc:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST, detail=str(exc)
        ) from exc
