"""Admin auth security hardening tests.

Run from main-app/admin/backend:
    python -m pytest app/tests -q
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clear_settings_cache():
    from app.config import get_settings
    get_settings.cache_clear()


def _reset_db_state():
    import app.database as db_mod
    db_mod._engine = None
    db_mod._SessionLocal = None


# ---------------------------------------------------------------------------
# validate_production_settings
# ---------------------------------------------------------------------------

class TestValidateProductionSettings:
    def test_dev_mode_always_empty(self, monkeypatch):
        """In dev mode, defaults raise no issues."""
        monkeypatch.setenv("APP_ENV", "development")
        monkeypatch.delenv("K_SERVICE", raising=False)
        _clear_settings_cache()
        try:
            from app.config import get_settings, validate_production_settings
            assert validate_production_settings(get_settings()) == []
        finally:
            _clear_settings_cache()

    def test_production_flags_default_jwt(self, monkeypatch):
        monkeypatch.setenv("K_SERVICE", "admin-svc")
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ENV", raising=False)
        _clear_settings_cache()
        try:
            from app.config import get_settings, validate_production_settings
            issues = validate_production_settings(get_settings())
            assert any("JWT_SECRET_KEY" in i for i in issues)
        finally:
            _clear_settings_cache()

    def test_production_flags_default_admin_password(self, monkeypatch):
        monkeypatch.setenv("K_SERVICE", "admin-svc")
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ENV", raising=False)
        _clear_settings_cache()
        try:
            from app.config import get_settings, validate_production_settings
            issues = validate_production_settings(get_settings())
            assert any("ADMIN_INIT_PASSWORD" in i for i in issues)
        finally:
            _clear_settings_cache()

    def test_production_flags_wildcard_cors(self, monkeypatch):
        monkeypatch.setenv("K_SERVICE", "admin-svc")
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ENV", raising=False)
        _clear_settings_cache()
        try:
            from app.config import get_settings, validate_production_settings
            issues = validate_production_settings(get_settings())
            assert any("CORS" in i for i in issues)
        finally:
            _clear_settings_cache()

    def test_production_flags_default_ingest_key(self, monkeypatch):
        monkeypatch.setenv("K_SERVICE", "admin-svc")
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ENV", raising=False)
        _clear_settings_cache()
        try:
            from app.config import get_settings, validate_production_settings
            issues = validate_production_settings(get_settings())
            assert any("INGEST_SECRET_KEY" in i for i in issues)
        finally:
            _clear_settings_cache()

    def test_production_clean_with_strong_settings(self, monkeypatch):
        """No issues when all production settings are properly configured."""
        monkeypatch.setenv("K_SERVICE", "admin-svc")
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ENV", raising=False)
        monkeypatch.setenv("JWT_SECRET_KEY", "x" * 40)
        monkeypatch.setenv("ADMIN_INIT_PASSWORD", "SuperStr0ng!Pass#2026")
        monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://admin.example.com")
        monkeypatch.setenv("INGEST_SECRET_KEY", "strong-ingest-secret-xyz-2026-abc")
        monkeypatch.setenv("FERNET_SECRET_KEY", "test-fernet-passphrase-used-only-in-unit-tests")
        _clear_settings_cache()
        try:
            from app.config import get_settings, validate_production_settings
            assert validate_production_settings(get_settings()) == []
        finally:
            _clear_settings_cache()

    def test_short_jwt_flagged_even_if_not_default(self, monkeypatch):
        """A non-default but short (<32 chars) JWT secret is still flagged."""
        monkeypatch.setenv("K_SERVICE", "admin-svc")
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ENV", raising=False)
        monkeypatch.setenv("JWT_SECRET_KEY", "short-key")
        monkeypatch.setenv("ADMIN_INIT_PASSWORD", "SuperStr0ng!Pass#2026")
        monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://admin.example.com")
        monkeypatch.setenv("INGEST_SECRET_KEY", "strong-ingest-secret-xyz-2026-abc")
        monkeypatch.setenv("FERNET_SECRET_KEY", "test-fernet-passphrase-used-only-in-unit-tests")
        _clear_settings_cache()
        try:
            from app.config import get_settings, validate_production_settings
            issues = validate_production_settings(get_settings())
            assert any("JWT_SECRET_KEY" in i for i in issues)
        finally:
            _clear_settings_cache()


# ---------------------------------------------------------------------------
# is_production() detection
# ---------------------------------------------------------------------------

class TestIsProduction:
    def test_k_service_means_production(self, monkeypatch):
        monkeypatch.setenv("K_SERVICE", "some-cloud-run-svc")
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ENV", raising=False)
        from app.config import is_production
        assert is_production() is True

    def test_app_env_development_overrides_k_service(self, monkeypatch):
        monkeypatch.setenv("K_SERVICE", "some-cloud-run-svc")
        monkeypatch.setenv("APP_ENV", "development")
        from app.config import is_production
        assert is_production() is False

    def test_app_env_production(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.delenv("K_SERVICE", raising=False)
        from app.config import is_production
        assert is_production() is True

    def test_no_env_vars_is_dev(self, monkeypatch):
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ENV", raising=False)
        monkeypatch.delenv("K_SERVICE", raising=False)
        from app.config import is_production
        assert is_production() is False


# ---------------------------------------------------------------------------
# Production lifespan guard: RuntimeError on default/weak JWT
# ---------------------------------------------------------------------------

class TestLifespanProductionGuard:
    def test_raises_on_default_jwt_in_production(self, monkeypatch):
        monkeypatch.setenv("K_SERVICE", "admin-svc")
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ENV", raising=False)
        _clear_settings_cache()
        try:
            with patch("app.main.init_db"):
                from app.main import lifespan, app as admin_app

                async def _run():
                    async with lifespan(admin_app):
                        pass

                with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
                    asyncio.run(_run())
        finally:
            _clear_settings_cache()

    def test_no_raise_in_dev_with_defaults(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "development")
        monkeypatch.delenv("K_SERVICE", raising=False)
        _clear_settings_cache()
        try:
            with patch("app.main.init_db"):
                from app.main import lifespan, app as admin_app

                async def _run():
                    async with lifespan(admin_app):
                        pass

                asyncio.run(_run())  # must not raise
        finally:
            _clear_settings_cache()


# ---------------------------------------------------------------------------
# Production init_db: skip admin user with default password
# ---------------------------------------------------------------------------

class TestInitDbProductionAdminSeed:
    def test_default_password_in_production_skips_admin(self, monkeypatch, tmp_path):
        monkeypatch.setenv("K_SERVICE", "admin-svc")
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ENV", raising=False)
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test_prod.db")
        _clear_settings_cache()
        _reset_db_state()
        try:
            from app.database import AdminUser, get_db, init_db
            init_db()
            session = next(get_db())
            try:
                count = session.query(AdminUser).count()
            finally:
                session.close()
            assert count == 0, "Admin user must NOT be created with default password in production"
        finally:
            _clear_settings_cache()
            _reset_db_state()

    def test_dev_mode_without_password_skips_admin(self, monkeypatch, tmp_path):
        monkeypatch.setenv("APP_ENV", "development")
        monkeypatch.delenv("K_SERVICE", raising=False)
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test_dev.db")
        _clear_settings_cache()
        _reset_db_state()
        try:
            from app.database import AdminUser, get_db, init_db
            init_db()
            session = next(get_db())
            try:
                count = session.query(AdminUser).count()
            finally:
                session.close()
            assert count == 0, "Admin user must not be created without an explicit password"
        finally:
            _clear_settings_cache()
            _reset_db_state()

    def test_production_strong_password_creates_admin(self, monkeypatch, tmp_path):
        monkeypatch.setenv("K_SERVICE", "admin-svc")
        monkeypatch.delenv("APP_ENV", raising=False)
        monkeypatch.delenv("ENV", raising=False)
        monkeypatch.setenv("ADMIN_INIT_PASSWORD", "SuperStr0ng!Pass#2026")
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/test_strong.db")
        _clear_settings_cache()
        _reset_db_state()
        try:
            from app.database import AdminUser, get_db, init_db
            init_db()
            session = next(get_db())
            try:
                count = session.query(AdminUser).count()
            finally:
                session.close()
            assert count == 1, "Admin user must be created in production with a strong password"
        finally:
            _clear_settings_cache()
            _reset_db_state()


# ---------------------------------------------------------------------------
# SPA path traversal protection
# ---------------------------------------------------------------------------

class TestSpaTraversal:
    def test_normal_path_within_dist(self, tmp_path):
        dist = (tmp_path / "dist").resolve()
        dist.mkdir()
        (dist / "index.html").write_text("<html>app</html>")

        resolved = (dist / "index.html").resolve()
        assert resolved.is_relative_to(dist)
        assert resolved.is_file()

    def test_nested_asset_within_dist(self, tmp_path):
        dist = (tmp_path / "dist").resolve()
        assets = dist / "assets"
        assets.mkdir(parents=True)
        (assets / "app.js").write_text("// app")

        resolved = (dist / "assets/app.js").resolve()
        assert resolved.is_relative_to(dist)

    def test_single_dotdot_blocked(self, tmp_path):
        dist = (tmp_path / "dist").resolve()
        dist.mkdir()
        secret = tmp_path / "secret.txt"
        secret.write_text("SECRET")

        resolved = (dist / "../secret.txt").resolve()
        assert not resolved.is_relative_to(dist)

    def test_double_dotdot_blocked(self, tmp_path):
        dist = (tmp_path / "dist").resolve()
        dist.mkdir()

        resolved = (dist / "../../etc/passwd").resolve()
        assert not resolved.is_relative_to(dist)

    def test_embedded_dotdot_blocked(self, tmp_path):
        dist = (tmp_path / "dist").resolve()
        assets = dist / "assets"
        assets.mkdir(parents=True)

        resolved = (dist / "assets/../../secret").resolve()
        assert not resolved.is_relative_to(dist)

    def test_absolute_path_string_blocked(self, tmp_path):
        dist = (tmp_path / "dist").resolve()
        dist.mkdir()

        # Path("/etc/passwd") joined to dist — resolve should expose the escape
        resolved = (dist / "/etc/passwd").resolve()
        assert not resolved.is_relative_to(dist)


# ---------------------------------------------------------------------------
# Token validation (no DB required)
# ---------------------------------------------------------------------------

class TestTokenValidation:
    def test_create_and_decode_roundtrip(self):
        from datetime import timedelta

        from jose import jwt

        from app.auth import create_access_token
        from app.config import get_settings

        token = create_access_token({"sub": "testuser"}, expires_delta=timedelta(hours=1))
        s = get_settings()
        payload = jwt.decode(token, s.JWT_SECRET_KEY, algorithms=[s.JWT_ALGORITHM])
        assert payload["sub"] == "testuser"
        assert "exp" in payload

    def test_tampered_token_rejected(self):
        from jose import JWTError, jwt

        from app.auth import create_access_token
        from app.config import get_settings

        token = create_access_token({"sub": "testuser"})
        tampered = token[:-5] + "XXXXX"
        s = get_settings()
        with pytest.raises(JWTError):
            jwt.decode(tampered, s.JWT_SECRET_KEY, algorithms=[s.JWT_ALGORITHM])

    def test_wrong_secret_rejected(self):
        from jose import JWTError, jwt

        from app.auth import create_access_token

        token = create_access_token({"sub": "testuser"})
        with pytest.raises(JWTError):
            jwt.decode(token, "wrong-secret-key-that-is-definitely-long-enough-x", algorithms=["HS256"])
