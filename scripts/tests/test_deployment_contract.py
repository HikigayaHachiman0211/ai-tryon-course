from __future__ import annotations

from pathlib import Path
import json
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
AZURE = ROOT / "deploy" / "azure"


def test_azure_release_artifacts_exist():
    expected = [
        AZURE / "README.md",
        AZURE / ".env.azure.example",
        AZURE / "compose.yaml",
        AZURE / "Caddyfile",
        AZURE / "systemd" / "ai-tryon-course.service",
        AZURE / "infra" / "main.bicep",
        AZURE / "infra" / "main.parameters.example.json",
        AZURE / "infra" / "cloud-init.yaml",
        *(AZURE / "scripts" / name for name in (
            "preflight.ps1",
            "provision.ps1",
            "configure-cost-controls.ps1",
            "render-local-test-env.ps1",
            "package-release.ps1",
            "upload-product-assets.ps1",
            "deploy.ps1",
            "smoke-test.ps1",
            "status.ps1",
            "backup.ps1",
            "restore.ps1",
            "rollback.ps1",
        )),
    ]
    missing = [str(path.relative_to(ROOT)) for path in expected if not path.is_file()]
    assert not missing, f"missing Azure release artifacts: {missing}"


def test_compose_declares_only_the_five_release_services_and_required_volumes():
    compose = (AZURE / "compose.yaml").read_text(encoding="utf-8")
    for service in ("postgres:", "main:", "admin:", "workbench:", "proxy:"):
        assert service in compose
    for volume in (
        "postgres-data:",
        "main-history:",
        "admin-data:",
        "admin-voice-clones:",
        "workbench-uploads:",
        "workbench-assets:",
        "workbench-history:",
        "caddy-data:",
        "caddy-config:",
    ):
        assert volume in compose
    assert "ports:" in compose
    assert '"80:80"' in compose
    assert '"443:443"' in compose
    assert '"8443:8443"' in compose
    assert '"9443:9443"' in compose


def test_bicep_exposes_only_expected_outputs_and_uses_amd64_vm_contract():
    bicep = (AZURE / "infra" / "main.bicep").read_text(encoding="utf-8")
    for token in (
        "Standard_B2als_v2",
        "Ubuntu",
        "disablePasswordAuthentication: true",
        "StandardSSD_LRS",
        "allowBlobPublicAccess: true",
        "product-assets",
        "course-media",
        "backups",
        "output vmResourceId",
        "output publicIpAddress",
        "output fqdn",
        "output storageAccountName",
    ):
        assert token in bicep


def test_deploy_installs_systemd_unit_before_enabling_it():
    deploy = (AZURE / "scripts" / "deploy.ps1").read_text(encoding="utf-8")
    assert "deploy/azure/systemd/ai-tryon-course.service" in deploy.replace("\\", "/")
    assert "install -m 0644" in deploy
    assert "systemctl enable ai-tryon-course.service" in deploy


def test_release_validation_rejects_missing_aliyun_assets(tmp_path):
    sys.path.insert(0, str(ROOT / "scripts" / "release"))
    from build_release import validate_release

    database = tmp_path / "main-app/database.json"
    database.parent.mkdir(parents=True)
    database.write_text(json.dumps([{}] * 4721), encoding="utf-8")
    for relative in (
        "main-app/backend/read-model/catalog.json",
        "tryon-workbench/read-model/catalog.i18n.json",
        "main-app/backend/app/i18n/catalog-translations/en.json",
        "main-app/backend/app/i18n/catalog-translations/ja.json",
        "main-app/admin/backend/app/db_init_job.py",
        "tryon-workbench/Dockerfile.worker",
        "tryon-workbench/app/queue_worker.py",
        "tryon-workbench/app/task_db.py",
        "tryon-workbench/app/task_queue.py",
        "tryon-workbench/app/video_config.py",
        "tryon-workbench/app/video_gateway.py",
        "tryon-workbench/app/video_routes.py",
        "tryon-workbench/app/video_tasks.py",
        "tryon-workbench/static/css/video.css",
        "tryon-workbench/static/js/video.js",
        "tryon-workbench/static/js/video-form.js",
        "main-app/admin/backend/app/routers/video_config.py",
        "main-app/admin/frontend/src/pages/VideoSettingsTab.tsx",
        "deploy/azure/compose.yaml",
        "deploy/azure/aca/main.bicep",
        "deploy/azure/aca/main.parameters.example.json",
        "deploy/azure/aca/.env.aca.example",
        "deploy/azure/scripts/deploy-aca.ps1",
        "deploy/azure/scripts/smoke-test-aca.ps1",
        "deploy/azure/scripts/upload-sample-models.ps1",
        "main-app/backend/app/oss_client.py",
        "main-app/admin/backend/app/services/oss_client.py",
        "tryon-workbench/app/oss_client.py",
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit, match="deploy/aliyun"):
        validate_release(tmp_path)
