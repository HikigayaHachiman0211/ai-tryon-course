import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import AIAPIProvider, AIFeatureConfig, Base, _seed_ai_configs


def test_admin_video_settings_encrypt_and_preserve_key():
    from app.routers.video_config import VideoConfigUpdate, get_config, update_config
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    admin = SimpleNamespace(username="test")
    with Session(engine) as db, patch("app.routers.video_config.encrypt_secret", side_effect=lambda value: "encrypted:" + value):
        _seed_ai_configs(db)
        assert db.query(AIAPIProvider).filter_by(provider_key="01router").one()
        saved = update_config(VideoConfigUpdate(enabled=True, api_key="private-video-key", project_id="project-a"), admin=admin, db=db)
        assert saved["has_api_key"]
        assert "private-video-key" not in str(saved)
        update_config(VideoConfigUpdate(enabled=False, api_key=" "), admin=admin, db=db)
        provider = db.query(AIAPIProvider).filter_by(provider_key="01router").one()
        assert provider.api_key_encrypted == "encrypted:private-video-key"
        feature = db.query(AIFeatureConfig).filter_by(feature_key="tryon_video").one()
        assert feature.config["project_id"] == "project-a"
        assert not feature.enabled
        assert get_config(admin=admin, db=db)["project_id"] == "project-a"
        update_config(VideoConfigUpdate(clear_api_key=True), admin=admin, db=db)
        assert not provider.api_key_encrypted
    engine.dispose()


def test_admin_video_connection_check_only_reads_and_does_not_expose_errors():
    from app.routers.video_config import test_config as check, VideoConfigUpdate, update_config
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    calls = []

    class Client:
        def __init__(self, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def get(self, url, **kwargs):
            calls.append((url, kwargs))
            return SimpleNamespace(status_code=200)

    with Session(engine) as db, patch("app.routers.video_config.encrypt_secret", side_effect=lambda v: v), patch("app.routers.video_config.decrypt_secret", side_effect=lambda v: v), patch("app.routers.video_config.httpx.AsyncClient", Client):
        admin = SimpleNamespace(username="test")
        update_config(VideoConfigUpdate(api_key="secret"), admin=admin, db=db)
        result = asyncio.run(check(admin=admin, db=db))
        assert result["success"]
        assert calls[0][0] == "https://01router.com/api/v1/generations"
        assert calls[0][1]["params"] == {"limit": 1}
        assert "secret" not in str(result)
        from app.routers.ai_config import test_provider
        provider = db.query(AIAPIProvider).filter_by(provider_key="01router").one()
        with patch("app.routers.ai_config.decrypt_secret", side_effect=lambda v: v):
            generic = asyncio.run(test_provider(provider.id, admin=admin, db=db))
        assert generic["success"]
        assert len(calls) == 2
    engine.dispose()
