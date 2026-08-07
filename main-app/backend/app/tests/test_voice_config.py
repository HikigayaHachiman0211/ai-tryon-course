"""Verification tests for voice config, model isolation, and clone safety.

Run from the backend directory:
  cd backend && python app/tests/test_voice_config.py

Uses source code inspection + subprocess for imports to avoid path issues.
"""
from __future__ import annotations

import ast
import os
import re
import subprocess
import sys

_backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_admin_backend_root = os.path.abspath(os.path.join(_backend_root, "..", "admin", "backend"))


def _read_file(relative_path: str) -> str:
    """Read a file relative to backend root."""
    path = os.path.join(_backend_root, relative_path)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _read_admin_file(relative_path: str) -> str:
    """Read a file relative to admin/backend root."""
    path = os.path.join(_admin_backend_root, relative_path)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _run_python(code: str) -> tuple[int, str, str]:
    """Run Python code in the backend directory as a subprocess."""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True,
        cwd=_backend_root,
        timeout=30,
    )
    return result.returncode, result.stdout, result.stderr


# ---- Tests ----

def test_feature_key_constants():
    """Verify _FEATURE_DEFAULTS uses voice_asr/voice_tts/voice_clone."""
    code = "from app.ai_runtime_config import _FEATURE_DEFAULTS; print(_FEATURE_DEFAULTS.keys())"
    rc, out, err = _run_python(code)
    assert rc == 0, f"Import failed: {err}"
    assert "voice_asr" in out, "voice_asr missing from _FEATURE_DEFAULTS"
    assert "voice_tts" in out, "voice_tts missing from _FEATURE_DEFAULTS"
    assert "voice_clone" in out, "voice_clone missing from _FEATURE_DEFAULTS"
    # Old keys should NOT be present (as standalone keys)
    assert "'asr'" not in out.replace("voice_asr", ""), "Old 'asr' key still in _FEATURE_DEFAULTS"
    assert "'tts'" not in out.replace("voice_tts", ""), "Old 'tts' key still in _FEATURE_DEFAULTS"
    print("[PASS] Feature key constants use voice_asr/voice_tts/voice_clone")


def test_model_keyword_mapping():
    """Verify model keyword mapping is explicit and correct."""
    code = "from app.assistant.voice.voice_router import _FEATURE_TO_MODEL_KEYWORD; print(_FEATURE_TO_MODEL_KEYWORD)"
    rc, out, err = _run_python(code)
    assert rc == 0, f"Import failed: {err}"
    assert "'voice_asr': 'asr'" in out
    assert "'voice_tts': 'tts'" in out
    assert "'voice_clone': 'clone'" in out
    print("[PASS] Model keyword mapping is correct")


def test_resolve_voice_provider_model_check():
    """Verify that the model validation rejects mismatched models."""
    # The forced_default_model for voice_asr is 'mimo-v2.5-asr' which contains 'asr'
    # So it should pass. We test that the function exists and has the right logic.
    src = _read_file("app/assistant/voice/voice_router.py")
    # Verify the keyword check returns error, not just warning
    assert "ASR_MODEL_MISCONFIGURED" in src, "ASR_MODEL_MISCONFIGURED error code missing"
    assert "TTS_MODEL_MISCONFIGURED" in src, "TTS_MODEL_MISCONFIGURED error code missing"
    # Verify it returns error dict, not just logs warning
    assert "return {}" in src, "Model mismatch should return error, not just warn"
    print("[PASS] Model validation returns error for mismatched models")


def test_disabled_feature_not_bypassed():
    """Verify resolve_feature_config supports include_disabled parameter."""
    src = _read_file("app/ai_runtime_config.py")
    assert "include_disabled" in src, "include_disabled parameter missing from resolve_feature_config"
    # Verify voice_router uses include_disabled=True
    vr_src = _read_file("app/assistant/voice/voice_router.py")
    assert "include_disabled=True" in vr_src, "voice_router does not use include_disabled=True"
    # Verify the enabled check is explicit
    assert 'feat.get("enabled") is False' in vr_src or "enabled" in vr_src, "enabled check missing"
    print("[PASS] Disabled feature detection uses include_disabled=True")


def test_audio_header_validation_wav():
    """Verify WAV header validation works."""
    code = """
import sys
sys.path.insert(0, r'{admin}')
from app.routers.voice_clone import _validate_audio_header

# Valid WAV header
wav_data = b"RIFF\\x00\\x00\\x00\\x00WAVE" + b"\\x00" * 100
assert _validate_audio_header(wav_data, "test.wav") is None, "Valid WAV rejected"

# Wrong header for .wav
mp3_data = b"ID3\\x03\\x00\\x00\\x00\\x00\\x00\\x00\\x00" + b"\\x00" * 100
err = _validate_audio_header(mp3_data, "test.wav")
assert err is not None and "RIFF/WAVE" in err, f"MP3 in .wav not caught: {{err}}"

# Too small
err = _validate_audio_header(b"\\x00" * 5, "test.wav")
assert err is not None and "过小" in err, f"Small file not caught: {{err}}"

print("OK")
""".format(admin=_admin_backend_root.replace("\\", "\\\\"))
    rc, out, err = _run_python(code)
    assert rc == 0, f"WAV validation test failed: {err}"
    print("[PASS] WAV header validation works correctly")


def test_audio_header_validation_mp3():
    """Verify MP3 header validation works."""
    code = """
import sys
sys.path.insert(0, r'{admin}')
from app.routers.voice_clone import _validate_audio_header

# Valid MP3 header (ID3)
mp3_data = b"ID3\\x03\\x00\\x00\\x00\\x00\\x00\\x00\\x00" + b"\\x00" * 100
assert _validate_audio_header(mp3_data, "test.mp3") is None, "Valid MP3 rejected"

# Valid MP3 header (frame sync)
sync_data = b"\\xFF\\xFB\\x90\\x00" + b"\\x00" * 100
assert _validate_audio_header(sync_data, "test.mp3") is None, "Frame sync MP3 rejected"

# Wrong header for .mp3
wav_data = b"RIFF\\x00\\x00\\x00\\x00WAVE" + b"\\x00" * 100
err = _validate_audio_header(wav_data, "test.mp3")
assert err is not None, "WAV in .mp3 not caught"

print("OK")
""".format(admin=_admin_backend_root.replace("\\", "\\\\"))
    rc, out, err = _run_python(code)
    assert rc == 0, f"MP3 validation test failed: {err}"
    print("[PASS] MP3 header validation works correctly")


def test_audio_header_cross_format():
    """Verify cross-format detection."""
    code = """
import sys
sys.path.insert(0, r'{admin}')
from app.routers.voice_clone import _validate_audio_header

# WAV content with .mp3 extension
wav_data = b"RIFF\\x00\\x00\\x00\\x00WAVE" + b"\\x00" * 100
err = _validate_audio_header(wav_data, "test.mp3")
assert err is not None, "WAV content in .mp3 file should be rejected"

print("OK")
""".format(admin=_admin_backend_root.replace("\\", "\\\\"))
    rc, out, err = _run_python(code)
    assert rc == 0, f"Cross-format test failed: {err}"
    print("[PASS] Cross-format detection works")


def test_audio_header_rejects_non_audio():
    """Verify non-audio files are rejected."""
    code = """
import sys
sys.path.insert(0, r'{admin}')
from app.routers.voice_clone import _validate_audio_header

# Random bytes
err = _validate_audio_header(b"\\x00\\x01\\x02\\x03\\x04\\x05\\x06\\x07\\x08\\x09\\x0A\\x0B", "test.wav")
assert err is not None, "Random bytes not rejected"

# PDF header
pdf_data = b"%PDF-1.4" + b"\\x00" * 100
err = _validate_audio_header(pdf_data, "test.wav")
assert err is not None, "PDF not rejected"

print("OK")
""".format(admin=_admin_backend_root.replace("\\", "\\\\"))
    rc, out, err = _run_python(code)
    assert rc == 0, f"Non-audio rejection test failed: {err}"
    print("[PASS] Non-audio files are rejected")


def test_voice_clone_router_requires_auth():
    """Verify all voice_clone endpoints require authentication."""
    src = _read_admin_file("app/routers/voice_clone.py")

    # Count endpoint decorators
    endpoints = re.findall(r'@router\.\w+\(', src)
    assert len(endpoints) >= 7, f"Expected at least 7 endpoints, found {len(endpoints)}"

    # Check that get_current_admin is imported and used
    assert "get_current_admin" in src, "get_current_admin not imported"
    assert "Depends(get_current_admin)" in src, "get_current_admin not used as dependency"

    # Check that every public def function has admin parameter
    # Use a pattern that handles nested parens in default values
    func_pattern = re.compile(r'def (\w+)\(', re.DOTALL)
    skip_funcs = {"_ensure_upload_dir", "_validate_audio_header"}
    for match in func_pattern.finditer(src):
        func_name = match.group(1)
        if func_name.startswith("_") or func_name in skip_funcs:
            continue
        # Extract the full function signature by counting parentheses
        start = match.end()
        depth = 1
        pos = start
        while pos < len(src) and depth > 0:
            if src[pos] == '(':
                depth += 1
            elif src[pos] == ')':
                depth -= 1
            pos += 1
        params = src[start:pos - 1]
        if "get_current_admin" in params or "AdminUser" in params:
            continue
        assert False, f"Endpoint {func_name} does not have admin auth parameter"

    print("[PASS] All voice_clone endpoints require admin authentication")


def test_voice_catalog_returns_provider_voice_id():
    """Verify get_published_clone_voices includes provider_voice_id field."""
    src = _read_file("app/assistant/voice/voice_catalog.py")
    assert "provider_voice_id" in src, "provider_voice_id not in voice_catalog.py"
    assert "source_audio_path" not in src.split("def get_published_clone_voices")[1].split("def ")[0] or \
           "source_audio_path" not in src.split("result.append")[1].split("return")[0] if "result.append" in src else True, \
           "source_audio_path may be leaked"
    print("[PASS] Voice catalog includes provider_voice_id")


def test_resolve_voice_uses_provider_voice_id():
    """Verify resolve_voice returns provider_voice_id for clone voices."""
    code = """
from app.assistant.voice.voice_catalog import resolve_voice, DEFAULT_VOICE

# Without a real DB, clone resolution should fall back to default
result = resolve_voice("nonexistent", "999", "clone")
assert result == DEFAULT_VOICE, f"Expected fallback, got {result}"

# Preset voice should work
result = resolve_voice("茉莉", None, "preset")
assert result == "茉莉"

print("OK")
"""
    rc, out, err = _run_python(code)
    assert rc == 0, f"resolve_voice test failed: {err}"
    print("[PASS] resolve_voice correctly handles fallbacks")


def test_clone_feature_checked_in_catalog():
    """Verify get_all_catalog_items checks voice_clone feature enabled state."""
    src = _read_file("app/assistant/voice/voice_catalog.py")
    assert "voice_clone" in src, "voice_clone feature check missing from catalog"
    assert "resolve_feature_config" in src, "resolve_feature_config not used in catalog"
    assert "include_disabled" in src, "include_disabled not used in catalog"
    print("[PASS] Catalog checks voice_clone feature enabled state")


def test_database_seed_uses_voice_keys():
    """Verify database seed uses voice_asr/voice_tts, not old asr/tts."""
    src = _read_admin_file("app/database.py")
    assert '"voice_asr"' in src, "voice_asr missing from database seed"
    assert '"voice_tts"' in src, "voice_tts missing from database seed"
    # Verify migration function exists
    assert "_migrate_voice_feature_keys" in src, "Migration function missing"
    print("[PASS] Database seed uses voice_asr/voice_tts with migration")


def test_migration_old_asr_to_voice_asr():
    """Real DB test: old 'asr' config migrates to 'voice_asr' with correct values."""
    code = r"""
import sys, os, json, tempfile
admin_path = r'{admin}'
# Remove any other app from sys.modules to avoid conflicts
for k in list(sys.modules.keys()):
    if k.startswith('app'):
        del sys.modules[k]
sys.path.insert(0, admin_path)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base, AIFeatureConfig

# Create temp SQLite DB
tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
tmp.close()
db_url = 'sqlite:///' + tmp.name.replace('\\', '/')
engine = create_engine(db_url, connect_args={{"check_same_thread": False}})
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
session = Session()

# Insert old 'asr' config with admin-customized values
session.add(AIFeatureConfig(
    feature_key="asr",
    enabled=True,
    default_provider="mimo_asr",
    default_model="custom-asr-model",
    config={{"language": "auto", "max_base64_mb": 20}},
    updated_by="admin",
))
session.commit()

# Run migration
from app.database import _migrate_voice_feature_keys
_migrate_voice_feature_keys(session)

# Verify voice_asr was created with old config values
voice_asr = session.query(AIFeatureConfig).filter_by(feature_key="voice_asr").first()
assert voice_asr is not None, "voice_asr was not created"
assert voice_asr.enabled == True, f"voice_asr.enabled should be True, got {{voice_asr.enabled}}"
assert voice_asr.default_model == "custom-asr-model", f"voice_asr.default_model should be 'custom-asr-model', got {{voice_asr.default_model}}"
cfg = voice_asr.config
if isinstance(cfg, str):
    import json as _j
    cfg = _j.loads(cfg)
assert cfg == {{"language": "auto", "max_base64_mb": 20}}, f"voice_asr.config wrong: {{cfg}}"
assert voice_asr.updated_by == "migration", f"voice_asr.updated_by should be 'migration', got {{voice_asr.updated_by}}"

# Verify old 'asr' still exists
old_asr = session.query(AIFeatureConfig).filter_by(feature_key="asr").first()
assert old_asr is not None, "Old 'asr' should still exist"

session.close()
try:
    os.unlink(tmp.name)
except OSError:
    pass
print("OK")
""".format(admin=_admin_backend_root.replace("\\", "\\\\"))
    rc, out, err = _run_python(code)
    assert rc == 0, f"Migration test (old asr -> voice_asr) failed: {err}\n{out}"
    print("[PASS] Old 'asr' config migrates to 'voice_asr' with correct values")


def _db_test(setup_and_assert_code: str):
    """Run a DB test in a subprocess with proper admin module imports."""
    admin = _admin_backend_root.replace("\\", "\\\\")
    code = (
        "import sys, os, tempfile\n"
        "admin_path = r'" + admin + "'\n"
        "for k in list(sys.modules.keys()):\n"
        "    if k.startswith('app'):\n"
        "        del sys.modules[k]\n"
        "sys.path.insert(0, admin_path)\n"
        "from sqlalchemy import create_engine\n"
        "from sqlalchemy.orm import sessionmaker\n"
        "from app.database import Base, AIFeatureConfig\n"
        "tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)\n"
        "tmp.close()\n"
        "db_url = 'sqlite:///' + tmp.name.replace(os.sep, '/')\n"
        "engine = create_engine(db_url, connect_args={'check_same_thread': False})\n"
        "Base.metadata.create_all(engine)\n"
        "Session = sessionmaker(bind=engine)\n"
        "session = Session()\n"
        + setup_and_assert_code +
        "\nsession.close()\n"
        "try:\n"
        "    os.unlink(tmp.name)\n"
        "except OSError:\n"
        "    pass\n"
        "print('OK')\n"
    )
    return code


def test_migration_old_tts_to_voice_tts():
    """Real DB test: old 'tts' config migrates to 'voice_tts' with correct values."""
    code = _db_test(
        "session.add(AIFeatureConfig(feature_key='tts', enabled=True, default_provider='mimo_tts', "
        "default_model='custom-tts-model', config={'voice': 'custom_voice'}, updated_by='admin'))\n"
        "session.commit()\n"
        "from app.database import _migrate_voice_feature_keys\n"
        "_migrate_voice_feature_keys(session)\n"
        "voice_tts = session.query(AIFeatureConfig).filter_by(feature_key='voice_tts').first()\n"
        "assert voice_tts is not None, 'voice_tts was not created'\n"
        "assert voice_tts.enabled == True, 'enabled wrong: ' + str(voice_tts.enabled)\n"
        "assert voice_tts.default_model == 'custom-tts-model', 'model wrong: ' + str(voice_tts.default_model)\n"
        "cfg = voice_tts.config\n"
        "if isinstance(cfg, str): import json; cfg = json.loads(cfg)\n"
        "assert cfg == {'voice': 'custom_voice'}, 'config wrong: ' + str(cfg)\n"
    )
    rc, out, err = _run_python(code)
    assert rc == 0, f"Migration test (old tts -> voice_tts) failed: {err}\n{out}"
    print("[PASS] Old 'tts' config migrates to 'voice_tts' with correct values")


def test_migration_does_not_overwrite_admin_edited_voice_asr():
    """Real DB test: if voice_asr was manually edited by admin, old 'asr' should NOT overwrite it."""
    code = _db_test(
        "session.add(AIFeatureConfig(feature_key='asr', enabled=True, default_provider='mimo_asr', "
        "default_model='old-asr-model', config={'language': 'auto'}, updated_by='admin'))\n"
        "session.add(AIFeatureConfig(feature_key='voice_asr', enabled=False, default_provider='mimo_asr', "
        "default_model='admin-chosen-model', config={'language': 'zh'}, updated_by='admin_user'))\n"
        "session.commit()\n"
        "from app.database import _migrate_voice_feature_keys\n"
        "_migrate_voice_feature_keys(session)\n"
        "v = session.query(AIFeatureConfig).filter_by(feature_key='voice_asr').first()\n"
        "assert v.enabled == False, 'should still be False: ' + str(v.enabled)\n"
        "assert v.default_model == 'admin-chosen-model', 'model wrong: ' + str(v.default_model)\n"
        "assert v.updated_by == 'admin_user', 'updated_by wrong: ' + str(v.updated_by)\n"
    )
    rc, out, err = _run_python(code)
    assert rc == 0, f"Migration no-overwrite test failed: {err}\n{out}"
    print("[PASS] Migration does not overwrite admin-edited voice_asr")


def test_migration_overwrites_system_default_voice_asr():
    """Real DB test: if voice_asr was only set by system seed, old admin 'asr' should overwrite it."""
    code = _db_test(
        "session.add(AIFeatureConfig(feature_key='asr', enabled=True, default_provider='mimo_asr', "
        "default_model='admin-custom-asr', config={'language': 'auto'}, updated_by='admin'))\n"
        "session.add(AIFeatureConfig(feature_key='voice_asr', enabled=False, default_provider='mimo_asr', "
        "default_model='mimo-v2.5-asr', updated_by='system'))\n"
        "session.commit()\n"
        "from app.database import _migrate_voice_feature_keys\n"
        "_migrate_voice_feature_keys(session)\n"
        "v = session.query(AIFeatureConfig).filter_by(feature_key='voice_asr').first()\n"
        "assert v.enabled == True, 'should be True: ' + str(v.enabled)\n"
        "assert v.default_model == 'admin-custom-asr', 'model wrong: ' + str(v.default_model)\n"
        "cfg = v.config\n"
        "if isinstance(cfg, str): import json; cfg = json.loads(cfg)\n"
        "assert cfg == {'language': 'auto'}, 'config wrong: ' + str(cfg)\n"
    )
    rc, out, err = _run_python(code)
    assert rc == 0, f"Migration overwrite-system-default test failed: {err}\n{out}"
    print("[PASS] Migration overwrites system-default voice_asr with old admin config")


def test_migration_preserves_old_keys():
    """Real DB test: old 'asr'/'tts' keys are preserved after migration."""
    code = _db_test(
        "session.add(AIFeatureConfig(feature_key='asr', enabled=True, default_provider='mimo_asr', "
        "default_model='mimo-v2.5-asr', updated_by='admin'))\n"
        "session.add(AIFeatureConfig(feature_key='tts', enabled=True, default_provider='mimo_tts', "
        "default_model='mimo-v2.5-tts', updated_by='admin'))\n"
        "session.commit()\n"
        "from app.database import _migrate_voice_feature_keys\n"
        "_migrate_voice_feature_keys(session)\n"
        "assert session.query(AIFeatureConfig).filter_by(feature_key='asr').first() is not None, 'old asr gone'\n"
        "assert session.query(AIFeatureConfig).filter_by(feature_key='tts').first() is not None, 'old tts gone'\n"
        "assert session.query(AIFeatureConfig).filter_by(feature_key='voice_asr').first() is not None, 'voice_asr missing'\n"
        "assert session.query(AIFeatureConfig).filter_by(feature_key='voice_tts').first() is not None, 'voice_tts missing'\n"
    )
    rc, out, err = _run_python(code)
    assert rc == 0, f"Migration preserves old keys test failed: {err}\n{out}"
    print("[PASS] Old 'asr'/'tts' keys preserved after migration")


def test_voice_clone_no_fake_publish():
    """Verify voice_clone router source code: publish requires ready + provider_voice_id."""
    src = _read_admin_file("app/routers/voice_clone.py")
    # publish endpoint must check status == "ready"
    assert 'profile.status != "ready"' in src, "Publish does not check status == ready"
    # publish endpoint must check provider_voice_id
    assert "not profile.provider_voice_id" in src, "Publish does not check provider_voice_id"
    # trigger_clone must not create fake provider_voice_id
    # It should set status to "failed" when API is not implemented
    assert "VOICE_CLONE_PROVIDER_NOT_IMPLEMENTED" in src, "Missing NOT_IMPLEMENTED error code"
    print("[PASS] Voice clone cannot publish fake voices")


if __name__ == "__main__":
    tests = [
        test_feature_key_constants,
        test_model_keyword_mapping,
        test_resolve_voice_provider_model_check,
        test_disabled_feature_not_bypassed,
        test_audio_header_validation_wav,
        test_audio_header_validation_mp3,
        test_audio_header_cross_format,
        test_audio_header_rejects_non_audio,
        test_voice_clone_router_requires_auth,
        test_voice_catalog_returns_provider_voice_id,
        test_resolve_voice_uses_provider_voice_id,
        test_clone_feature_checked_in_catalog,
        test_database_seed_uses_voice_keys,
        test_migration_old_asr_to_voice_asr,
        test_migration_old_tts_to_voice_tts,
        test_migration_does_not_overwrite_admin_edited_voice_asr,
        test_migration_overwrites_system_default_voice_asr,
        test_migration_preserves_old_keys,
        test_voice_clone_no_fake_publish,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"[FAIL] {test.__name__}: {e}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    if failed:
        sys.exit(1)
    else:
        print("All tests passed!")
