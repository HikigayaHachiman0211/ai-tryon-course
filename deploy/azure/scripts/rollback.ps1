[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$SshHost,
    [Parameter(Mandatory = $true)][string]$SshUsername,
    [Parameter(Mandatory = $true)][string]$SshPrivateKeyPath,
    [Parameter(Mandatory = $true)][string]$PreviousReleaseId,
    [Parameter(Mandatory = $true)][ValidatePattern('^[a-zA-Z0-9.-]+$')][string]$AzureFqdn,
    [Parameter(Mandatory = $false)][string]$RemoteRoot = '/opt/ai-tryon-course',
    [Parameter(Mandatory = $false)][switch]$ConfirmRollback,
    [Parameter(Mandatory = $false)][switch]$ConfirmDatabaseCompatibility
)

. (Join-Path $PSScriptRoot 'common.ps1')

if (-not $ConfirmRollback) { throw 'Rollback is state-changing; pass -ConfirmRollback after selecting the verified previous release.' }
if (-not $ConfirmDatabaseCompatibility) { throw 'Inspect release/database compatibility first; pass -ConfirmDatabaseCompatibility or run restore.ps1 before rollback.' }
if ($PreviousReleaseId -notmatch '^[A-Za-z0-9._-]+$') { throw 'PreviousReleaseId contains unsafe characters.' }

$privateKeyPath = (Resolve-Path -LiteralPath $SshPrivateKeyPath).Path
$remote = "$SshUsername@$SshHost"
$remoteScript = @"
set -eu
REMOTE_ROOT='$RemoteRoot'
RELEASE_ID='$PreviousReleaseId'
CURRENT="`$REMOTE_ROOT/current"
TARGET="`$REMOTE_ROOT/releases/`$RELEASE_ID"
ENV_FILE="`$REMOTE_ROOT/shared/azure.env"
COMPOSE_FILE="`$TARGET/deploy/azure/compose.yaml"
test -d "`$TARGET"
test -f "`$TARGET/SHA256SUMS"
test -f "`$ENV_FILE"
(cd "`$TARGET" && sha256sum -c SHA256SUMS)
test -f "`$COMPOSE_FILE"
ln -sfn "`$TARGET" "`$CURRENT"
export COMPOSE_PARALLEL_LIMIT=1
/usr/bin/docker compose --env-file "`$ENV_FILE" -f "`$CURRENT/deploy/azure/compose.yaml" config --quiet
/usr/bin/docker compose --env-file "`$ENV_FILE" -f "`$CURRENT/deploy/azure/compose.yaml" build --progress plain main
/usr/bin/docker compose --env-file "`$ENV_FILE" -f "`$CURRENT/deploy/azure/compose.yaml" build --progress plain admin
/usr/bin/docker compose --env-file "`$ENV_FILE" -f "`$CURRENT/deploy/azure/compose.yaml" build --progress plain workbench
/usr/bin/docker compose --env-file "`$ENV_FILE" -f "`$CURRENT/deploy/azure/compose.yaml" up -d postgres admin workbench main proxy
sudo systemctl restart ai-tryon-course.service
printf 'rollback_release=%s\n' "`$RELEASE_ID"
"@

Invoke-CheckedNative -CommandName 'ssh' -ArgumentList @('-i', $privateKeyPath, '-o', 'BatchMode=yes', $remote, $remoteScript) -Context 'verify immutable previous release and switch the current symlink' | ForEach-Object { $_ }
$repositoryRoot = Get-RepositoryRoot
$smokeScript = Join-Path $PSScriptRoot 'smoke-test.ps1'
& $smokeScript -AzureFqdn $AzureFqdn -EvidencePath (Join-Path $repositoryRoot 'evidence\azure\rollback-smoke.json')
Invoke-CheckedNative -CommandName 'node' -ArgumentList @((Join-Path $repositoryRoot 'scripts\i18n\check_resource_parity.mjs')) -Context 'rerun root locale resource parity after rollback' | Out-Null
Invoke-CheckedNative -CommandName 'node' -ArgumentList @((Join-Path $repositoryRoot 'scripts\i18n\check_visible_literals.mjs'), '--strict', '--all') -Context 'rerun root visible-literal locale gate after rollback' | Out-Null
Invoke-CheckedNative -CommandName 'python' -ArgumentList @((Join-Path $repositoryRoot 'scripts\i18n\check_catalog_coverage.py')) -Context 'rerun catalog locale coverage after rollback' | Out-Null
Write-Output "rolled back to release: $PreviousReleaseId"
Write-Output 'Rollback health, TLS, core smoke, and locale gates passed. No Docker volumes were removed.'
