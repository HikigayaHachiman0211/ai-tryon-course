[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$SshHost,
    [Parameter(Mandatory = $true)][string]$SshUsername,
    [Parameter(Mandatory = $true)][string]$SshPrivateKeyPath,
    [Parameter(Mandatory = $false)][ValidateSet('azure', 'aliyun')][string]$DeploymentTarget = 'azure',
    [Parameter(Mandatory = $false)][string]$RemoteRoot = '/opt/ai-tryon-course',
    [Parameter(Mandatory = $false)][string]$BackupLabel = ''
)

. (Join-Path $PSScriptRoot 'common.ps1')

$privateKeyPath = (Resolve-Path -LiteralPath $SshPrivateKeyPath).Path
$remote = "$SshUsername@$SshHost"
if ([string]::IsNullOrWhiteSpace($BackupLabel)) {
    $BackupLabel = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
}
if ($BackupLabel -notmatch '^[A-Za-z0-9._-]+$') { throw 'BackupLabel contains unsafe characters.' }

$remoteScript = @"
set -eu
umask 077
REMOTE_ROOT='$RemoteRoot'
RELEASE_ROOT="`$REMOTE_ROOT/releases"
CURRENT="`$REMOTE_ROOT/current"
ENV_FILE="`$REMOTE_ROOT/shared/$DeploymentTarget.env"
BACKUP_DIR="`$REMOTE_ROOT/backups/$BackupLabel"
COMPOSE_FILE="`$CURRENT/deploy/$DeploymentTarget/compose.yaml"
POSTGRES_IMAGE='postgres:16-alpine@sha256:7a396fd264a2067788b6551122b50f162bf6136312c7fc9d74381cb92c648382'

test -f "`$ENV_FILE"
test -f "`$COMPOSE_FILE"
PROJECT=`$(docker compose --env-file "`$ENV_FILE" -f "`$COMPOSE_FILE" config --format json | jq -r '.name')
test -n "`$PROJECT" && test "`$PROJECT" != null
mkdir -p "`$BACKUP_DIR/volumes"
mkdir -p "`$BACKUP_DIR/application-file"
chmod 700 "`$BACKUP_DIR" "`$BACKUP_DIR/volumes"
export COMPOSE_PARALLEL_LIMIT=1

docker compose --env-file "`$ENV_FILE" -f "`$COMPOSE_FILE" config --images > "`$BACKUP_DIR/compose-images.txt"
POSTGRES_VERSION=`$(docker compose --env-file "`$ENV_FILE" -f "`$COMPOSE_FILE" exec -T postgres sh -c 'psql -At -U "`$POSTGRES_USER" -d "`$POSTGRES_DB" -c "SHOW server_version;"' | tr -d '\\r\\n')
test -n "`$POSTGRES_VERSION"
docker compose --env-file "`$ENV_FILE" -f "`$COMPOSE_FILE" exec -T postgres sh -c 'pg_dump -Fc --no-owner --no-acl -U "`$POSTGRES_USER" -d "`$POSTGRES_DB"' > "`$BACKUP_DIR/postgres.dump"
cp "`$CURRENT/deploy/$DeploymentTarget/compose.yaml" "`$BACKUP_DIR/application-file/deploy-compose.yaml"
if test -f "`$CURRENT/release-manifest.json"; then cp "`$CURRENT/release-manifest.json" "`$BACKUP_DIR/release-manifest.json"; fi

for volume in `$(docker volume ls --filter label=com.docker.compose.project="`$PROJECT" --format '{{.Name}}'); do
    safe_name=`$(printf '%s' "`$volume" | tr '/:' '__')
    docker run --rm --mount "type=volume,src=`$volume,dst=/source,readonly" "`$POSTGRES_IMAGE" sh -c 'tar -C /source -czf - .' > "`$BACKUP_DIR/volumes/`$safe_name.tgz"
done

cat > "`$BACKUP_DIR/metadata.json" <<EOF
{
  "created_at_utc": "`$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "release": "`$(readlink "`$CURRENT" || true)",
  "backup_label": "$BackupLabel",
  "postgres_server_version": "`$POSTGRES_VERSION",
  "database_dump": "postgres.dump",
  "application_file": "application-file/deploy-compose.yaml",
  "volume_archives": [`$(find "`$BACKUP_DIR/volumes" -maxdepth 1 -type f -printf '"%f"\n' | sort | paste -sd, -)]
}
EOF
chmod 600 "`$BACKUP_DIR/postgres.dump" "`$BACKUP_DIR/metadata.json" "`$BACKUP_DIR/compose-images.txt" "`$BACKUP_DIR/application-file/deploy-compose.yaml"
if test -f "`$BACKUP_DIR/release-manifest.json"; then chmod 600 "`$BACKUP_DIR/release-manifest.json"; fi
(cd "`$BACKUP_DIR" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
chmod 600 "`$BACKUP_DIR/SHA256SUMS"
printf 'backup_complete=%s\n' "`$BACKUP_DIR"
"@

Invoke-CheckedNative -CommandName 'ssh' -ArgumentList @('-i', $privateKeyPath, '-o', 'BatchMode=yes', $remote, $remoteScript) -Context 'create PostgreSQL and named-volume backup without printing secrets' | ForEach-Object { $_ }
Write-Output "remote backup created: $RemoteRoot/backups/$BackupLabel"
Write-Output 'Backup contents include PostgreSQL custom-format data, all Compose-managed named volumes, image metadata, and SHA256SUMS.'
