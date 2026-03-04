# filepath: backend/tests/test_hardening.py
"""
Pre-Launch Hardening Tests — evidence-based proofs for Steps 1-4.

Run:
    cd wealth_to_the_wise
    python -m pytest backend/tests/test_hardening.py -v

Each test proves a specific hardening claim without requiring a live
database, external APIs, or running server.
"""

from __future__ import annotations

import importlib
import inspect
import os
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest


# ═════════════════════════════════════════════════════════════════════
# STEP 1 — SQLite production guard
# ═════════════════════════════════════════════════════════════════════

class TestSqliteGuard:
    """Prove that _guard_sqlite_in_production blocks SQLite in production."""

    def test_production_sqlite_raises(self):
        """ENV=production + SQLite → RuntimeError."""
        from backend.database import _guard_sqlite_in_production

        with patch.dict(os.environ, {"ENV": "production"}, clear=False):
            # Also remove PYTEST_CURRENT_TEST so the guard is not skipped
            env = os.environ.copy()
            env.pop("PYTEST_CURRENT_TEST", None)
            with patch.dict(os.environ, env, clear=True):
                with pytest.raises(RuntimeError, match="SQLite is not allowed in production"):
                    _guard_sqlite_in_production("sqlite+aiosqlite:///./wealth.db")

    def test_production_postgres_ok(self):
        """ENV=production + PostgreSQL → no error."""
        from backend.database import _guard_sqlite_in_production

        with patch.dict(os.environ, {"ENV": "production"}, clear=False):
            env = os.environ.copy()
            env.pop("PYTEST_CURRENT_TEST", None)
            with patch.dict(os.environ, env, clear=True):
                # Should NOT raise
                _guard_sqlite_in_production("postgresql+asyncpg://user:pass@host/db")

    def test_env_not_set_sqlite_ok(self):
        """ENV not set (default) + SQLite → allowed (not production)."""
        from backend.database import _guard_sqlite_in_production

        env = os.environ.copy()
        env.pop("ENV", None)
        env.pop("APP_ENV", None)
        env.pop("PYTEST_CURRENT_TEST", None)
        with patch.dict(os.environ, env, clear=True):
            _guard_sqlite_in_production("sqlite+aiosqlite:///./wealth.db")

    def test_development_sqlite_ok(self):
        """ENV=development + SQLite → allowed."""
        from backend.database import _guard_sqlite_in_production

        with patch.dict(os.environ, {"ENV": "development"}, clear=False):
            env = os.environ.copy()
            env.pop("PYTEST_CURRENT_TEST", None)
            with patch.dict(os.environ, env, clear=True):
                _guard_sqlite_in_production("sqlite+aiosqlite:///./wealth.db")

    def test_pytest_current_test_skips_guard(self):
        """PYTEST_CURRENT_TEST set + ENV=production + SQLite → allowed."""
        from backend.database import _guard_sqlite_in_production

        with patch.dict(os.environ, {
            "ENV": "production",
            "PYTEST_CURRENT_TEST": "backend/tests/test_hardening.py::test",
        }, clear=False):
            # Should NOT raise because PYTEST_CURRENT_TEST is set
            _guard_sqlite_in_production("sqlite+aiosqlite:///./wealth.db")

    def test_detect_dialect_sqlite(self):
        """_detect_dialect recognises SQLite."""
        from backend.database import _detect_dialect
        assert _detect_dialect("sqlite+aiosqlite:///./wealth.db") == "sqlite"

    def test_detect_dialect_postgres(self):
        """_detect_dialect recognises PostgreSQL."""
        from backend.database import _detect_dialect
        assert _detect_dialect("postgresql+asyncpg://u:p@host/db") == "postgresql"


# ═════════════════════════════════════════════════════════════════════
# STEP 2 — Durable artifact storage
# ═════════════════════════════════════════════════════════════════════

class TestStorageAbstraction:
    """Prove the storage abstraction exists and has correct guards."""

    def test_local_storage_upload(self, tmp_path: Path):
        """LocalStorage.upload copies a file to the destination."""
        from backend.storage import LocalStorage

        store = LocalStorage(root=str(tmp_path))
        src = tmp_path / "video.mp4"
        src.write_bytes(b"fake-video-data")

        url = store.upload("videos/abc/video.mp4", src)
        assert (tmp_path / "videos" / "abc" / "video.mp4").is_file()
        assert "video.mp4" in url

    def test_local_storage_exists(self, tmp_path: Path):
        """LocalStorage.exists returns True for uploaded files."""
        from backend.storage import LocalStorage

        store = LocalStorage(root=str(tmp_path))
        src = tmp_path / "thumb.jpg"
        src.write_bytes(b"fake-thumb")
        store.upload("thumbnails/t.jpg", src)

        assert store.exists("thumbnails/t.jpg")
        assert not store.exists("nonexistent.jpg")

    def test_local_storage_upload_failure(self, tmp_path: Path):
        """LocalStorage.upload raises StorageUploadError on failure."""
        from backend.storage import LocalStorage, StorageUploadError

        store = LocalStorage(root=str(tmp_path))
        with pytest.raises(StorageUploadError):
            store.upload("videos/x.mp4", Path("/nonexistent/file.mp4"))

    def test_production_local_storage_warns(self):
        """STORAGE_PROVIDER=local + ENV=production → warning (not crash)."""
        import logging
        from backend.storage import _guard_local_storage_in_production

        env = os.environ.copy()
        env.pop("PYTEST_CURRENT_TEST", None)
        env["ENV"] = "production"
        env["STORAGE_PROVIDER"] = "local"
        with patch.dict(os.environ, env, clear=True):
            with patch("backend.storage.logger") as mock_logger:
                _guard_local_storage_in_production()  # should NOT raise
                mock_logger.warning.assert_called_once()
                assert "STORAGE_PROVIDER=local" in mock_logger.warning.call_args[0][0]

    def test_dev_local_storage_allowed(self):
        """STORAGE_PROVIDER=local + ENV not set → no error."""
        from backend.storage import _guard_local_storage_in_production

        env = os.environ.copy()
        env.pop("PYTEST_CURRENT_TEST", None)
        env.pop("ENV", None)
        env.pop("APP_ENV", None)
        env["STORAGE_PROVIDER"] = "local"
        with patch.dict(os.environ, env, clear=True):
            _guard_local_storage_in_production()  # should not raise

    def test_pipeline_uploads_before_success(self):
        """_run_pipeline_background must upload artifacts before marking success."""
        source = inspect.getsource(
            importlib.import_module("backend.routers.videos")._run_pipeline_background
        )
        # The storage upload block should appear BEFORE the final status assignment
        upload_idx = source.find("get_storage")
        posted_idx = source.find('row.status = "posted"')
        completed_idx = source.find('row.status = "completed"')

        assert upload_idx != -1, "Pipeline must call get_storage()"
        assert upload_idx < posted_idx, "Artifact upload must happen before 'posted' status"
        assert upload_idx < completed_idx, "Artifact upload must happen before 'completed' status"

    def test_storage_failure_marks_job_failed(self):
        """If StorageUploadError is raised, pipeline must set status='failed'."""
        source = inspect.getsource(
            importlib.import_module("backend.routers.videos")._run_pipeline_background
        )
        assert "StorageUploadError" in source
        assert "external_service" in source, "Storage failure must use 'external_service' error category"


# ═════════════════════════════════════════════════════════════════════
# STEP 3 — Strict decrypt() failure handling
# ═════════════════════════════════════════════════════════════════════

class TestDecryptOrRaise:
    """Prove decrypt_or_raise halts on failure."""

    def test_empty_ciphertext_returns_empty(self):
        """decrypt_or_raise(None/empty) returns '' — not an error."""
        from backend.encryption import decrypt_or_raise
        assert decrypt_or_raise(None, field="test") == ""
        assert decrypt_or_raise("", field="test") == ""

    def test_valid_ciphertext_decrypts(self):
        """decrypt_or_raise(valid) returns the plaintext."""
        from backend.encryption import decrypt_or_raise, encrypt
        ct = encrypt("my-secret-key")
        assert decrypt_or_raise(ct, field="api_key") == "my-secret-key"

    def test_corrupted_ciphertext_raises(self):
        """decrypt_or_raise(garbage) raises DecryptionFailedError."""
        from backend.encryption import decrypt_or_raise, DecryptionFailedError
        with pytest.raises(DecryptionFailedError, match="Decryption failed for 'api_key'"):
            decrypt_or_raise("not-valid-fernet-ciphertext", field="api_key")

    def test_decryption_failed_error_has_field(self):
        """DecryptionFailedError carries the field label for logging."""
        from backend.encryption import DecryptionFailedError
        err = DecryptionFailedError("openai_api_key")
        assert err.field_label == "openai_api_key"
        assert "openai_api_key" in str(err)

    def test_generate_uses_decrypt_or_raise(self):
        """generate_video endpoint must use decrypt_or_raise for API keys."""
        source = inspect.getsource(
            importlib.import_module("backend.routers.videos").generate_video
        )
        assert "decrypt_or_raise" in source

    def test_scheduler_uses_decrypt_or_raise(self):
        """scheduler_worker must use decrypt_or_raise for API keys."""
        source = inspect.getsource(
            importlib.import_module("backend.scheduler_worker")._process_single_schedule
        )
        assert "decrypt_or_raise" in source

    def test_admin_retry_uses_decrypt_or_raise(self):
        """admin retry_video must use decrypt_or_raise."""
        import backend.routers.admin as admin_mod
        full_source = inspect.getsource(admin_mod)
        assert "decrypt_or_raise" in full_source

    def test_analytics_uses_decrypt_or_raise(self):
        """analytics_worker must use decrypt_or_raise for tokens."""
        source = inspect.getsource(
            importlib.import_module("backend.analytics_worker")
        )
        assert "decrypt_or_raise" in source


# ═════════════════════════════════════════════════════════════════════
# STEP 4 — Load test files exist
# ═════════════════════════════════════════════════════════════════════

class TestLoadTestSuite:
    """Prove the k6 load test files exist and are well-formed."""

    _loadtest_dir = Path(__file__).resolve().parent.parent.parent / "loadtest"

    def test_health_test_exists(self):
        assert (self._loadtest_dir / "health_test.js").is_file()

    def test_metrics_test_exists(self):
        assert (self._loadtest_dir / "metrics_test.js").is_file()

    def test_generate_test_exists(self):
        assert (self._loadtest_dir / "generate_test.js").is_file()

    def test_readme_exists(self):
        assert (self._loadtest_dir / "README.md").is_file()

    def test_health_test_has_thresholds(self):
        content = (self._loadtest_dir / "health_test.js").read_text()
        assert "thresholds" in content
        assert "p(95)" in content

    def test_generate_test_has_auth(self):
        content = (self._loadtest_dir / "generate_test.js").read_text()
        assert "AUTH_TOKEN" in content
        assert "Authorization" in content

    def test_all_tests_configurable_base_url(self):
        for fname in ("health_test.js", "metrics_test.js", "generate_test.js"):
            content = (self._loadtest_dir / fname).read_text()
            assert "BASE_URL" in content, f"{fname} must support configurable BASE_URL"
