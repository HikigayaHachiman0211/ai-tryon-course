from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.routers.sample_models import _resolve_image_url


def _model(gcs_url: str | None):
    return SimpleNamespace(
        gender="男",
        image_filename="mannequin-male-1.png",
        gcs_url=gcs_url,
    )


def test_storage_url_uses_current_bucket(monkeypatch):
    expected = "https://storage.googleapis.com/current-bucket/sample_models/男/mannequin-male-1.png"
    monkeypatch.setattr(
        "app.routers.sample_models.gcs.get_blob_url",
        lambda name: f"https://storage.googleapis.com/current-bucket/{name}",
    )

    old_url = "https://storage.googleapis.com/old-bucket/sample_models/男/mannequin-male-1.png"
    assert _resolve_image_url(_model(old_url)) == expected


def test_missing_url_uses_current_bucket(monkeypatch):
    monkeypatch.setattr(
        "app.routers.sample_models.gcs.get_blob_url",
        lambda name: f"https://storage.googleapis.com/current-bucket/{name}",
    )

    assert _resolve_image_url(_model(None)).endswith("/sample_models/男/mannequin-male-1.png")


def test_external_url_is_preserved():
    url = "https://cdn.example.com/models/mannequin-male-1.png"
    assert _resolve_image_url(_model(url)) == url


def test_seed_uses_configured_bucket():
    from app import database

    session = Mock()
    settings = SimpleNamespace(GCS_BUCKET_NAME="current-bucket")
    with patch.object(database, "get_settings", return_value=settings):
        database._seed_sample_models(session)

    seeded_models = [call.args[0] for call in session.add.call_args_list]
    assert seeded_models
    assert all(
        model.gcs_url.startswith("https://storage.googleapis.com/current-bucket/")
        for model in seeded_models
    )
    session.commit.assert_called_once()
