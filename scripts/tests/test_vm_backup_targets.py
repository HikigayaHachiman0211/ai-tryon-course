import base64
from hashlib import sha256
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]


def _run_powershell(script: str):
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    result = subprocess.run(["pwsh", "-NoLogo", "-NoProfile", "-EncodedCommand", encoded],
                            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    assert result.returncode == 0, result.stderr


def _quoted(path: Path) -> str:
    return str(path).replace("'", "''")


def test_backup_targets_the_chosen_cloud_without_contacting_ssh(tmp_path):
    key = tmp_path / "test-key"
    key.write_text("test", encoding="utf-8")
    backup = ROOT / "deploy/azure/scripts/backup.ps1"
    remote = tmp_path / "backup-command.sh"
    script = r'''
$ErrorActionPreference = 'Stop'
$global:remoteScripts = @()
function global:ssh { $global:LASTEXITCODE = 0; $global:remoteScripts += [string]$args[-1] }
& '__BACKUP__' -SshHost test -SshUsername test -SshPrivateKeyPath '__KEY__' -BackupLabel test -DeploymentTarget aliyun
& '__BACKUP__' -SshHost test -SshUsername test -SshPrivateKeyPath '__KEY__' -BackupLabel test
if (-not $global:remoteScripts[0].Contains('shared/aliyun.env') -or -not $global:remoteScripts[0].Contains('deploy/aliyun/compose.yaml')) { throw 'Aliyun backup target mismatch' }
if (-not $global:remoteScripts[1].Contains('shared/azure.env') -or -not $global:remoteScripts[1].Contains('deploy/azure/compose.yaml')) { throw 'Azure backup target mismatch' }
if (-not $global:remoteScripts[0].Contains("config --format json | jq -r '.name'")) { throw 'backup does not use the configured Compose project name' }
Set-Content -LiteralPath '__REMOTE__' -Value $global:remoteScripts[0] -Encoding utf8
'''.replace("__BACKUP__", _quoted(backup)).replace("__KEY__", _quoted(key)).replace("__REMOTE__", _quoted(remote))
    _run_powershell(script)


def test_aliyun_restore_defaults_to_staging_only_without_contacting_cloud(tmp_path):
    key = tmp_path / "test-key"
    key.write_text("test", encoding="utf-8")
    backup = tmp_path / "backup"
    (backup / "application-file").mkdir(parents=True)
    (backup / "postgres.dump").write_bytes(b"test-dump")
    (backup / "application-file/deploy-compose.yaml").write_text("services: {}", encoding="utf-8")
    (backup / "metadata.json").write_text(json.dumps({"postgres_server_version": "16.4"}), encoding="utf-8")
    entries = []
    for name in ("postgres.dump", "application-file/deploy-compose.yaml", "metadata.json"):
        entries.append(f"{sha256((backup / name).read_bytes()).hexdigest()}  ./{name}")
    (backup / "SHA256SUMS").write_text("\n".join(entries) + "\n", encoding="utf-8")
    restore = ROOT / "deploy/azure/scripts/restore.ps1"
    remote = tmp_path / "restore-command.sh"
    script = r'''
$ErrorActionPreference = 'Stop'
$global:remoteScripts = @()
function global:ssh { $global:LASTEXITCODE = 0; $global:remoteScripts += [string]$args[-1] }
function global:scp { $global:LASTEXITCODE = 0 }
& '__RESTORE__' -SshHost test -SshUsername test -SshPrivateKeyPath '__KEY__' -BackupDirectory '__DIR__' -DeploymentTarget aliyun
$body = $global:remoteScripts[-1]
if (-not $body.Contains('shared/aliyun.env') -or -not $body.Contains('deploy/aliyun/compose.yaml')) { throw 'Aliyun restore target mismatch' }
if (-not $body.Contains("APPLY_PRODUCTION='0'")) { throw 'restore must default to staging' }
if (-not $body.Contains('CURRENT_POSTGRES_MAJOR="${CURRENT_POSTGRES_VERSION%%.*}"')) { throw 'PostgreSQL version check is broken' }
if (-not $body.Contains('createdb -U "$POSTGRES_USER" "$1"')) { throw 'staging database argument was lost' }
Set-Content -LiteralPath '__REMOTE__' -Value $body -Encoding utf8
'''.replace("__RESTORE__", _quoted(restore)).replace("__KEY__", _quoted(key)).replace("__DIR__", _quoted(backup)).replace("__REMOTE__", _quoted(remote))
    _run_powershell(script)
