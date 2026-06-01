"""No-mock tests for the onboarding storage abstraction (build-order §D).

R2 credentials are absent in the test env, so ``_use_object_storage()`` is
False and every call exercises the local-disk branch. We use a unique key
under ``uploads/onboarding/`` and clean it up afterwards. Nothing is mocked.
"""

import os
import uuid
from pathlib import Path

import pytest
from src.onboarding import storage


def _unique_key() -> str:
    """A collision-free disk key (mirrors the service's per-template shape)."""
    return f"onboarding_templates/test/{uuid.uuid4().hex}.pdf"


@pytest.mark.asyncio
async def test_storage_uses_disk_branch_in_test_env():
    """Without R2 creds the storage layer must take the disk branch."""
    from src.attachments.service import _use_object_storage

    assert _use_object_storage() is False


@pytest.mark.asyncio
async def test_write_read_serve_exists_delete_round_trip():
    """write→ref, exists, read_bytes/serve round-trip exact bytes, delete clears."""
    key = _unique_key()
    content = b"%PDF-1.4 onboarding storage round-trip " + uuid.uuid4().bytes
    ref = None
    try:
        ref = await storage.write(key, content, "application/pdf")

        # Disk ref is relative to the shared uploads/ root, NOT an obj:// ref.
        assert not ref.startswith(storage._OBJ_PREFIX)
        assert ref.startswith("onboarding/")

        # The file actually exists on disk and via the abstraction.
        assert (storage._UPLOADS_ROOT / ref).is_file()
        assert await storage.exists(ref) is True

        # read_bytes and serve both round-trip the exact bytes.
        assert await storage.read_bytes(ref) == content
        assert await storage.serve(ref) == content

        # Delete removes it; exists flips to False.
        await storage.delete(ref)
        assert await storage.exists(ref) is False
        assert not (storage._UPLOADS_ROOT / ref).exists()
        ref = None
    finally:
        # Defensive cleanup if an assertion fired mid-test.
        if ref is not None:
            leftover = storage._UPLOADS_ROOT / ref
            if leftover.exists():
                leftover.unlink()


@pytest.mark.asyncio
async def test_delete_missing_disk_ref_is_noop():
    """Deleting a ref that was never written must not raise (best-effort)."""
    key = _unique_key()
    ref = str((storage.ONBOARDING_DIR / key).relative_to(storage._UPLOADS_ROOT))
    assert await storage.exists(ref) is False
    # Should be a silent no-op, not a FileNotFoundError.
    await storage.delete(ref)
    assert await storage.exists(ref) is False


@pytest.mark.asyncio
async def test_write_creates_nested_parent_dirs():
    """write() must mkdir intermediate dirs for a deep key."""
    key = f"onboarding_templates/{uuid.uuid4().hex}/deep/nested/file.pdf"
    content = b"%PDF-1.4 nested"
    ref = None
    try:
        ref = await storage.write(key, content)
        path = storage._UPLOADS_ROOT / ref
        assert path.is_file()
        assert path.read_bytes() == content
    finally:
        if ref is not None:
            await storage.delete(ref)
            # Prune the now-empty unique parent tree we created.
            parent = (storage._UPLOADS_ROOT / ref).parent
            root = Path(storage.ONBOARDING_DIR)
            while parent != root and parent.exists() and not any(parent.iterdir()):
                parent.rmdir()
                parent = parent.parent


@pytest.mark.asyncio
async def test_write_disk_error_normalized_to_runtime_error():
    """A disk WRITE error (PermissionError / ENOSPC / EROFS) is normalized to
    RuntimeError so callers map it to 503 — mirroring read_bytes.

    No mocks: we create a real read-only directory under the uploads root and
    write into it, so ``write_bytes`` hits a genuine ``PermissionError`` (an
    OSError that is NOT FileNotFoundError). Without the normalization this would
    escape the callers' ``except RuntimeError`` as an opaque 500. Root bypasses
    Unix permissions, so skip there.
    """
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root bypasses file perms")

    subdir = f"test_ro_{uuid.uuid4().hex}"
    ro_dir = storage.ONBOARDING_DIR / subdir
    ro_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(ro_dir, 0o500)  # read + execute, NOT writable
        with pytest.raises(RuntimeError):
            await storage.write(
                f"{subdir}/blocked.pdf", b"%PDF-1.4", "application/pdf"
            )
    finally:
        os.chmod(ro_dir, 0o755)
        for child in ro_dir.iterdir():
            child.unlink()
        ro_dir.rmdir()


@pytest.mark.asyncio
async def test_read_bytes_unreadable_file_raises_runtime_error():
    """A disk read error (PermissionError, an OSError that is NOT a missing
    file) is normalized to RuntimeError so the router maps it to 503.

    No mocks: we ``write`` a real file, ``chmod 0o000`` it so the on-disk
    ``read_bytes`` hits a genuine ``PermissionError`` (a subclass of OSError
    but not FileNotFoundError), and assert the abstraction surfaces a
    ``RuntimeError`` rather than the bare OSError — proving the 503 mapping in
    ``storage.read_bytes``. Root bypasses Unix file permissions, so skip there.
    """
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root bypasses file perms")

    key = _unique_key()
    content = b"%PDF-1.4 onboarding unreadable " + uuid.uuid4().bytes
    ref = await storage.write(key, content, "application/pdf")
    path = storage._UPLOADS_ROOT / ref
    try:
        os.chmod(path, 0o000)
        with pytest.raises(RuntimeError):
            await storage.read_bytes(ref)
    finally:
        # Restore perms so the file is readable/removable during cleanup.
        os.chmod(path, 0o644)
        if path.exists():
            path.unlink()
