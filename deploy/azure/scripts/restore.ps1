[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$SshHost,
    [Parameter(Mandatory = $true)][string]$SshUsername,
    [Parameter(Mandatory = $true)][string]$SshPrivateKeyPath,
    [Parameter(Mandatory = $true)][string]$BackupDirectory,
    [Parameter(Mandatory = $false)][ValidateSet('azure', 'aliyun')][string]$DeploymentTarget = 'azure',
    [Parameter(Mandatory = $false)][string]$RemoteRoot = '/opt/ai-tryon-course',
    [Parameter(Mandatory = $false)][switch]$ApplyToProduction,
    [Parameter(Mandatory = $false)][switch]$ConfirmProductionRestore
)

. (Join-Path $PSScriptRoot 'common.ps1')

$privateKeyPath = (Resolve-Path -LiteralPath $SshPrivateKeyPath).Path
$backupPath = (Resolve-Path -LiteralPath $BackupDirectory).Path
$dumpPath = Join-Path $backupPath 'postgres.dump'
$checksumsPath = Join-Path $backupPath 'SHA256SUMS'
$metadataPath = Join-Path $backupPath 'metadata.json'
$applicationFilePath = Join-Path $backupPath 'application-file\deploy-compose.yaml'
if (-not (Test-Path -LiteralPath $dumpPath -PathType Leaf)) { throw 'BackupDirectory must contain postgres.dump.' }
if (-not (Test-Path -LiteralPath $checksumsPath -PathType Leaf)) { throw 'BackupDirectory must contain SHA256SUMS.' }
if (-not (Test-Path -LiteralPath $metadataPath -PathType Leaf)) { throw 'BackupDirectory must contain metadata.json with PostgreSQL version metadata.' }
if (-not (Test-Path -LiteralPath $applicationFilePath -PathType Leaf)) { throw 'BackupDirectory must contain application-file/deploy-compose.yaml for the restore rehearsal.' }
if ($ApplyToProduction -and -not $ConfirmProductionRestore) {
    throw 'Production restore requires both -ApplyToProduction and -ConfirmProductionRestore.'
}

$metadata = Get-Content -LiteralPath $metadataPath -Raw | ConvertFrom-Json
$postgresVersion = [string]$metadata.postgres_server_version
if ($postgresVersion -notmatch '^\d+(\.\d+)+') { throw 'metadata.json has no usable PostgreSQL server version.' }
$expectedPostgresMajor = ($postgresVersion -split '\.')[0]

$checksumEntries = @{}
foreach ($line in Get-Content -LiteralPath $checksumsPath) {
    if ([string]::IsNullOrWhiteSpace($line)) { continue }
    if ($line -notmatch '^\s*([0-9a-fA-F]{64})\s+\*?(.+?)\s*$') { throw "Invalid SHA256SUMS line: $line" }
    $checksumEntries[$matches[2].Trim()] = $matches[1].ToLowerInvariant()
}
if (-not $checksumEntries.ContainsKey('./postgres.dump') -and -not $checksumEntries.ContainsKey('postgres.dump')) {
    throw 'SHA256SUMS has no postgres.dump entry.'
}
$expectedHash = if ($checksumEntries.ContainsKey('./postgres.dump')) { $checksumEntries['./postgres.dump'] } else { $checksumEntries['postgres.dump'] }
foreach ($entry in $checksumEntries.GetEnumerator()) {
    $relative = [string]$entry.Key -replace '^[.][\\/]', ''
    if ($relative.Contains('..')) { throw "Unsafe path in SHA256SUMS: $($entry.Key)" }
    $candidate = Join-Path $backupPath ($relative -replace '/', [System.IO.Path]::DirectorySeparatorChar)
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { throw "Checksum file is missing from backup: $relative" }
    $actual = (Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $entry.Value) { throw "Checksum mismatch in backup: $relative" }
}
$actualHash = (Get-FileHash -LiteralPath $dumpPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($expectedHash -ne $actualHash) { throw 'postgres.dump SHA256 does not match SHA256SUMS.' }
$applicationFileHash = (Get-FileHash -LiteralPath $applicationFilePath -Algorithm SHA256).Hash.ToLowerInvariant()

$remote = "$SshUsername@$SshHost"
$transferName = "restore-$([Guid]::NewGuid().ToString('N')).dump"
$remoteDump = "$RemoteRoot/incoming/$transferName"
$remoteApplicationFile = "$RemoteRoot/incoming/restore-$([Guid]::NewGuid().ToString('N')).compose.yaml"
Invoke-CheckedNative -CommandName 'ssh' -ArgumentList @('-i', $privateKeyPath, '-o', 'BatchMode=yes', $remote, "mkdir -p '$RemoteRoot/incoming' '$RemoteRoot/shared' && chmod 700 '$RemoteRoot/incoming'") -Context 'prepare restore staging directory' | Out-Null
Invoke-CheckedNative -CommandName 'scp' -ArgumentList @('-i', $privateKeyPath, $dumpPath, "$remote`:$remoteDump") -Context 'transfer verified PostgreSQL backup' | Out-Null
Invoke-CheckedNative -CommandName 'scp' -ArgumentList @('-i', $privateKeyPath, $applicationFilePath, "$remote`:$remoteApplicationFile") -Context 'transfer verified disposable application file for restore rehearsal' | Out-Null

$applyFlag = if ($ApplyToProduction) { '1' } else { '0' }
$remoteScript = @"
set -eu
umask 077
REMOTE_ROOT='$RemoteRoot'
CURRENT="`$REMOTE_ROOT/current"
ENV_FILE="`$REMOTE_ROOT/shared/$DeploymentTarget.env"
COMPOSE_FILE="`$CURRENT/deploy/$DeploymentTarget/compose.yaml"
DUMP='$remoteDump'
APPLICATION_FILE='$remoteApplicationFile'
EXPECTED_APPLICATION_HASH='$applicationFileHash'
EXPECTED_POSTGRES_MAJOR='$expectedPostgresMajor'
APPLY_PRODUCTION='$applyFlag'
STAGING_DB="restore_check_`$(date -u +%Y%m%d%H%M%S)_`$$"
PRE_RESTORE_DIR="`$REMOTE_ROOT/backups/pre-restore-`$(date -u +%Y%m%d%H%M%S)"
export COMPOSE_PARALLEL_LIMIT=1
test -f "`$ENV_FILE"
test -f "`$COMPOSE_FILE"
test -s "`$DUMP"
test -s "`$APPLICATION_FILE"
CURRENT_POSTGRES_VERSION=`$(docker compose --env-file "`$ENV_FILE" -f "`$COMPOSE_FILE" exec -T postgres sh -c 'psql -At -U "`$POSTGRES_USER" -d "`$POSTGRES_DB" -c "SHOW server_version;"' | tr -d '\\r\\n')
CURRENT_POSTGRES_MAJOR="`${CURRENT_POSTGRES_VERSION%%.*}"
if [ "`$CURRENT_POSTGRES_MAJOR" != "`$EXPECTED_POSTGRES_MAJOR" ]; then
    echo "PostgreSQL major version mismatch: backup=`$EXPECTED_POSTGRES_MAJOR current=`$CURRENT_POSTGRES_MAJOR" >&2
    exit 1
fi
mkdir -p "`$PRE_RESTORE_DIR"
docker compose --env-file "`$ENV_FILE" -f "`$COMPOSE_FILE" exec -T postgres sh -c 'pg_dump -Fc --no-owner --no-acl -U "`$POSTGRES_USER" -d "`$POSTGRES_DB"' > "`$PRE_RESTORE_DIR/postgres.dump"
printf '%s\\n' "`$CURRENT_POSTGRES_VERSION" > "`$PRE_RESTORE_DIR/postgres-server-version.txt"
(cd "`$PRE_RESTORE_DIR" && sha256sum postgres.dump postgres-server-version.txt > SHA256SUMS)
chmod 600 "`$PRE_RESTORE_DIR"/*
cleanup() {
    docker compose --env-file "`$ENV_FILE" -f "`$COMPOSE_FILE" exec -T postgres sh -c 'dropdb --if-exists -U "`$POSTGRES_USER" "`$1"' -- "`$STAGING_DB" >/dev/null 2>&1 || true
    rm -f "`$DUMP" "`$APPLICATION_FILE" "`$REHEARSAL_FILE"
}
trap cleanup EXIT

REHEARSAL_FILE="`$REMOTE_ROOT/incoming/restore-rehearsal-compose.yaml"
cp "`$APPLICATION_FILE" "`$REHEARSAL_FILE"
ACTUAL_APPLICATION_HASH=`$(sha256sum "`$REHEARSAL_FILE" | awk '{print `$1}')
if [ "`$ACTUAL_APPLICATION_HASH" != "`$EXPECTED_APPLICATION_HASH" ]; then
    echo 'Disposable application-file restore checksum mismatch.' >&2
    exit 1
fi
printf 'disposable_application_file=verified\\n'

docker compose --env-file "`$ENV_FILE" -f "`$COMPOSE_FILE" exec -T postgres sh -c 'createdb -U "`$POSTGRES_USER" "`$1"' -- "`$STAGING_DB"
cat "`$DUMP" | docker compose --env-file "`$ENV_FILE" -f "`$COMPOSE_FILE" exec -T postgres sh -c 'pg_restore --exit-on-error --no-owner --no-acl -U "`$POSTGRES_USER" -d "`$1" -' -- "`$STAGING_DB"
docker compose --env-file "`$ENV_FILE" -f "`$COMPOSE_FILE" exec -T postgres sh -c 'psql -At -U "`$POSTGRES_USER" -d "`$1" -c "SELECT count(*) FROM information_schema.tables WHERE table_schema = chr(112)||chr(117)||chr(98)||chr(108)||chr(105)||chr(99);"' -- "`$STAGING_DB"
PRODUCT_TABLES=`$(docker compose --env-file "`$ENV_FILE" -f "`$COMPOSE_FILE" exec -T postgres sh -c 'psql -At -U "`$POSTGRES_USER" -d "`$1" -c "SELECT count(*) FROM information_schema.tables WHERE table_schema = chr(112)||chr(117)||chr(98)||chr(108)||chr(105)||chr(99) AND table_name = chr(112)||chr(114)||chr(111)||chr(100)||chr(117)||chr(99)||chr(116)||chr(115);"' -- "`$STAGING_DB")
if [ "`$PRODUCT_TABLES" -ne 1 ]; then echo 'Restored database has no products table.' >&2; exit 1; fi
PRODUCT_COUNT=`$(docker compose --env-file "`$ENV_FILE" -f "`$COMPOSE_FILE" exec -T postgres sh -c 'psql -At -U "`$POSTGRES_USER" -d "`$1" -c "SELECT count(*) FROM products;"' -- "`$STAGING_DB")
if [ "`$PRODUCT_COUNT" -ne 4721 ]; then echo "Restored product count is not 4721: `$PRODUCT_COUNT" >&2; exit 1; fi
ADMIN_COUNT=`$(docker compose --env-file "`$ENV_FILE" -f "`$COMPOSE_FILE" exec -T postgres sh -c 'psql -At -U "`$POSTGRES_USER" -d "`$1" -c "SELECT count(*) FROM admin_users;"' -- "`$STAGING_DB")
if [ "`$ADMIN_COUNT" -lt 1 ]; then echo 'Restored database has no Admin login row.' >&2; exit 1; fi
jq -e '.product_count == 4721 and (.items | length) == 4721' "`$CURRENT/main-app/backend/read-model/catalog.json" >/dev/null
jq -e '.product_count == 4721 and (.items | length) == 4721' "`$CURRENT/tryon-workbench/read-model/catalog.i18n.json" >/dev/null
printf 'staging_integrity=products_4721_admin_login_read_models_ok\\n'
docker compose --env-file "`$ENV_FILE" -f "`$COMPOSE_FILE" exec -T postgres sh -c 'dropdb --if-exists -U "`$POSTGRES_USER" "`$1"' -- "`$STAGING_DB"

if [ "`$APPLY_PRODUCTION" = '1' ]; then
    docker compose --env-file "`$ENV_FILE" -f "`$COMPOSE_FILE" stop main admin workbench proxy
    cat "`$DUMP" | docker compose --env-file "`$ENV_FILE" -f "`$COMPOSE_FILE" exec -T postgres sh -c 'pg_restore --exit-on-error --clean --if-exists --no-owner --no-acl -U "`$POSTGRES_USER" -d "`$POSTGRES_DB" -'
    docker compose --env-file "`$ENV_FILE" -f "`$COMPOSE_FILE" up -d postgres admin workbench main proxy
    printf 'production_restore=applied\n'
else
    printf 'production_restore=not_applied\n'
fi
"@

Invoke-CheckedNative -CommandName 'ssh' -ArgumentList @('-i', $privateKeyPath, '-o', 'BatchMode=yes', $remote, $remoteScript) -Context 'restore verified PostgreSQL backup to staging, optionally production' | ForEach-Object { $_ }
if ($ApplyToProduction) {
    Write-Output 'PostgreSQL restore applied after staging validation; the application containers were restarted.'
} else {
    Write-Output 'PostgreSQL restore validated in a temporary database and not applied to production.'
}
