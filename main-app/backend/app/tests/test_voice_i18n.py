from __future__ import annotations

from app.assistant.voice.schemas import ASRResponse, VoiceCatalogItem
from app.assistant.voice.voice_catalog import localize_voice_item


def test_voice_ids_are_stable_while_display_names_change_by_locale():
    source = {"id": "茉莉", "name": "茉莉", "source": "preset", "description": "温柔女声（默认）"}
    english = localize_voice_item(source, "en")
    japanese = localize_voice_item(source, "ja")
    assert english["id"] == japanese["id"] == "茉莉"
    assert english["display_name"] == "Jasmine"
    assert japanese["display_name"] == "ジャスミン"
    assert "温柔" not in english["display_description"]


def test_japanese_voice_description_is_preserved():
    source = {"id": "voice-1", "source": "clone", "description": "落ち着いた男性の声"}
    assert localize_voice_item(source, "ja")["display_description"] == source["description"]


def test_voice_error_contract_has_stable_code_and_locale():
    response = ASRResponse(
        success=False,
        language="ja",
        speech_language="ja",
        locale="en",
        error={"code": "ASR_FAILED", "message": "Speech recognition failed."},
    )
    assert response.error["code"] == "ASR_FAILED"
    assert response.locale == "en"
    assert response.speech_language == "ja"
    assert VoiceCatalogItem(id="voice-1", name="voice-1", display_name="Voice 1").display_name == "Voice 1"
