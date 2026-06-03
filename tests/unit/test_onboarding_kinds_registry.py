"""No-mock unit tests for the onboarding DocumentType plugin registry (v3 §B).

These prove the P0 foundation's anti-silent-no-op defense: a NON-optional
Protocol + an import-time presence self-test that fails LOUDLY when a handler
omits any contract member. No DB and no mocks — the registry, the Protocol, and
the presence guard are pure in-process objects, exercised directly.

P2/P3 extend this matrix with real-PG required_satisfied / scrub-deletes-files /
view-gate assertions over all KIND_HANDLERS.
"""

import pytest
from src.onboarding.kinds import (
    KIND_HANDLERS,
    DocumentType,
    get_handler,
    register,
)

# --- exactly the one handler is registered at import -----------------------


def test_production_kinds_registered_after_import():
    """The three v3 production kinds auto-register on import — a new kind is
    added by dropping a file with a module-level ``HANDLER`` into the package."""
    assert {"esign_pdf", "questionnaire", "upload_request"} <= set(KIND_HANDLERS)


def test_get_handler_returns_registered_handler():
    """get_handler('esign_pdf') returns the live registered handler."""
    handler = get_handler("esign_pdf")
    assert handler is KIND_HANDLERS["esign_pdf"]
    assert handler.kind == "esign_pdf"


def test_get_handler_unknown_kind_raises_keyerror():
    """An unregistered kind is a hard error, never a silent no-op."""
    with pytest.raises(KeyError):
        get_handler("nope")


def test_registered_handler_is_a_documenttype():
    """The handler structurally satisfies the runtime_checkable Protocol."""
    assert isinstance(get_handler("esign_pdf"), DocumentType)


# --- register() presence self-test rejects malformed handlers --------------
#
# Each dummy is a deliberately-broken handler missing exactly one requirement.
# register() must raise TypeError AND leave KIND_HANDLERS untouched (a rejected
# handler's kind must never appear) — that is the guard that kills the "a new
# kind silently no-ops a security/completion step" failure class.


class _FullDummy:
    """A handler that satisfies the whole contract (the control case)."""

    kind = "dummy_full"
    needs_pdf_copy = False
    produces_signature = False
    records_view_via_stream = False

    def validate_definitions(self, defs, *, pdf_bytes):
        return None

    def validate_value(self, field, value):
        return value, None

    def required_satisfied(self, field, values, uploads, secrets):
        return True

    async def produce_artifact(self, db, *, doc, packet, signature_png, dry_run=False):
        return None

    async def scrub(self, db, *, doc):
        return None


def _make_missing_method() -> object:
    """A handler with NO ``scrub`` member at all (attribute absent)."""
    cls = type(
        "MissingMethodHandler", (), {
            "kind": "dummy_missing_method",
            "needs_pdf_copy": False,
            "produces_signature": False,
            "records_view_via_stream": False,
            "validate_definitions": _FullDummy.validate_definitions,
            "validate_value": _FullDummy.validate_value,
            "required_satisfied": _FullDummy.required_satisfied,
            "produce_artifact": _FullDummy.produce_artifact,
            # scrub intentionally absent → TypeError
        },
    )
    return cls()


def _make_missing_attr() -> object:
    """A handler with NO ``records_view_via_stream`` member at all."""
    cls = type(
        "MissingAttrHandler", (), {
            "kind": "dummy_missing_attr",
            "needs_pdf_copy": False,
            "produces_signature": False,
            # records_view_via_stream intentionally absent
            "validate_definitions": _FullDummy.validate_definitions,
            "validate_value": _FullDummy.validate_value,
            "required_satisfied": _FullDummy.required_satisfied,
            "produce_artifact": _FullDummy.produce_artifact,
            "scrub": _FullDummy.scrub,
        },
    )
    return cls()


def _make_empty_kind() -> object:
    """A fully-formed handler whose ``kind`` is an empty string."""
    cls = type(
        "EmptyKindHandler", (), {
            "kind": "",  # empty → rejected
            "needs_pdf_copy": False,
            "produces_signature": False,
            "records_view_via_stream": False,
            "validate_definitions": _FullDummy.validate_definitions,
            "validate_value": _FullDummy.validate_value,
            "required_satisfied": _FullDummy.required_satisfied,
            "produce_artifact": _FullDummy.produce_artifact,
            "scrub": _FullDummy.scrub,
        },
    )
    return cls()


def _make_nonstr_kind() -> object:
    """A fully-formed handler whose ``kind`` is not a str."""
    cls = type(
        "NonStrKindHandler", (), {
            "kind": 123,  # non-str → rejected
            "needs_pdf_copy": False,
            "produces_signature": False,
            "records_view_via_stream": False,
            "validate_definitions": _FullDummy.validate_definitions,
            "validate_value": _FullDummy.validate_value,
            "required_satisfied": _FullDummy.required_satisfied,
            "produce_artifact": _FullDummy.produce_artifact,
            "scrub": _FullDummy.scrub,
        },
    )
    return cls()


def test_register_rejects_handler_missing_method():
    """A handler with no ``scrub`` → TypeError, and KIND_HANDLERS is untouched."""
    bad = _make_missing_method()
    with pytest.raises(TypeError):
        register(bad)
    assert "dummy_missing_method" not in KIND_HANDLERS


def test_register_rejects_handler_missing_attr():
    """A handler with no ``records_view_via_stream`` → TypeError; not registered."""
    bad = _make_missing_attr()
    with pytest.raises(TypeError):
        register(bad)
    assert "dummy_missing_attr" not in KIND_HANDLERS


def test_register_rejects_empty_kind():
    """An empty-string ``kind`` → TypeError; the empty key never lands."""
    bad = _make_empty_kind()
    with pytest.raises(TypeError):
        register(bad)
    assert "" not in KIND_HANDLERS


def test_register_rejects_nonstr_kind():
    """A non-str ``kind`` → TypeError; the bad key never lands."""
    bad = _make_nonstr_kind()
    with pytest.raises(TypeError):
        register(bad)
    assert 123 not in KIND_HANDLERS


def test_register_accepts_full_handler_then_restore():
    """A handler that satisfies the whole contract registers cleanly.

    Registered under a throwaway kind and removed afterward so the production
    registry other tests rely on is not perturbed.
    """
    good = _FullDummy()
    try:
        returned = register(good)
        assert returned is good
        assert KIND_HANDLERS["dummy_full"] is good
    finally:
        KIND_HANDLERS.pop("dummy_full", None)
    # The throwaway kind is gone and the real registry is intact.
    assert "dummy_full" not in KIND_HANDLERS
    assert "esign_pdf" in KIND_HANDLERS


# --- the kind-parametrized contract matrix (skeleton; phases extend it) ----
#
# P2/P3 extend this matrix with real-PG required_satisfied / scrub-deletes-files
# / view-gate assertions over all KIND_HANDLERS. For now it pins the presence +
# type shape of every registered handler's contract surface.

_CONTRACT_ATTRS = {
    "kind": str,
    "needs_pdf_copy": bool,
    "produces_signature": bool,
    "records_view_via_stream": bool,
}
_CONTRACT_CALLABLES = (
    "validate_definitions",
    "validate_value",
    "required_satisfied",
    "produce_artifact",
    "scrub",
)


@pytest.mark.parametrize("kind", sorted(KIND_HANDLERS))
def test_registered_handler_exposes_full_contract(kind):
    """Every registered handler carries the 4 typed attrs and 5 callables."""
    handler = KIND_HANDLERS[kind]
    assert handler.kind == kind

    for attr, expected_type in _CONTRACT_ATTRS.items():
        assert hasattr(handler, attr), f"{kind!r} missing attr {attr!r}"
        assert isinstance(getattr(handler, attr), expected_type), (
            f"{kind!r}.{attr} is not a {expected_type.__name__}"
        )

    for method in _CONTRACT_CALLABLES:
        assert hasattr(handler, method), f"{kind!r} missing method {method!r}"
        assert callable(getattr(handler, method)), (
            f"{kind!r}.{method} is not callable"
        )
