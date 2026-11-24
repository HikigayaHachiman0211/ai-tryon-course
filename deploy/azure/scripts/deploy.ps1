[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$SshHost,
    [Parameter(Mandatory = $true)][string]$SshUsername,
    [Parameter(Mandatory = $true)][string]$SshPrivateKeyPath,
    [Parameter(Mandatory = $true)][string]$ReleaseArchive,
    [Parameter(Mandatory = $true)][string]$ProductionEnvPath,
    [Parameter(Mandatory = $false)][string]$RemoteRoot = '/opt/ai-tryon-course'
)

. (Join-Path $PSScriptRoot 'common.ps1')

$archivePath = (Resolve-Path -LiteralPath $ReleaseArchive).Path
$privateKeyPath = (Resolve-Path -LiteralPath $SshPrivateKeyPath).Path
$productionEnv = (Resolve-Path -LiteralPath $ProductionEnvPath).Path
$archiveHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
$archiveName = Split-Path -Leaf $archivePath
$releaseId = [System.IO.Path]::GetFileNameWithoutExtension($archiveName)
$remote = "$SshUsername@$SshHost"

$repositoryPrefix = ((Get-RepositoryRoot).TrimEnd('\') + '\')
if ($productionEnv.StartsWith($repositoryPrefix, [System.StringComparison]::OrdinalIgnoreCase)) { throw 'ProductionEnvPath must be outside the Git repository.' }
if ((Get-Item -LiteralPath $productionEnv).Length -eq 0) { throw 'Production environment file is empty.' }

Invoke-CheckedNative -CommandName 'ssh' -ArgumentList @('-i', $privateKeyPath, '-o', 'BatchMode=yes', $remote, "mkdir -p $RemoteRoot/incoming $RemoteRoot/releases $RemoteRoot/shared $RemoteRoot/backups") -Context 'prepare release directories on the named VM' | Out-Null
Invoke-CheckedNative -CommandName 'scp' -ArgumentList @('-i', $privateKeyPath, $archivePath, "$remote`:$RemoteRoot/incoming/$archiveName") -Context 'transfer immutable release archive' | Out-Null
Invoke-CheckedNative -CommandName 'scp' -ArgumentList @('-i', $privateKeyPath, $productionEnv, "$remote`:$RemoteRoot/shared/azure.env") -Context 'transfer production environment file without printing it' | Out-Null

$remoteScript = @"
set -eu
chmod 600 '$RemoteRoot/shared/azure.env'
printf '%s  %s\n' '$archiveHash' '$RemoteRoot/incoming/$archiveName' > '$RemoteRoot/incoming/$archiveName.sha256'
cd '$RemoteRoot/incoming'
sha256sum -c '$archiveName.sha256'
mkdir -p '$RemoteRoot/releases/$releaseId'
unzip -q -o '$archiveName' -d '$RemoteRoot/releases/$releaseId'
test -f '$RemoteRoot/releases/$releaseId/deploy/azure/compose.yaml'
ln -sfn '$RemoteRoot/releases/$releaseId' '$RemoteRoot/current'
export COMPOSE_PARALLEL_LIMIT=1
/usr/bin/docker compose --env-file '$RemoteRoot/shared/azure.env' -f '$RemoteRoot/current/deploy/azure/compose.yaml' config --quiet
/usr/bin/docker compose --env-file '$RemoteRoot/shared/azure.env' -f '$RemoteRoot/current/deploy/azure/compose.yaml' build --progress plain main
/usr/bin/docker compose --env-file '$RemoteRoot/shared/azure.env' -f '$RemoteRoot/current/deploy/azure/compose.yaml' build --progress plain admin
/usr/bin/docker compose --env-file '$RemoteRoot/shared/azure.env' -f '$RemoteRoot/current/deploy/azure/compose.yaml' build --progress plain workbench
/usr/bin/docker compose --env-file '$RemoteRoot/shared/azure.env' -f '$RemoteRoot/current/deploy/azure/compose.yaml' up -d postgres
/usr/bin/docker compose --env-file '$RemoteRoot/shared/azure.env' -f '$RemoteRoot/current/deploy/azure/compose.yaml' up -d admin
/usr/bin/docker compose --env-file '$RemoteRoot/shared/azure.env' -f '$RemoteRoot/current/deploy/azure/compose.yaml' up -d workbench
/usr/bin/docker compose --env-file '$RemoteRoot/shared/azure.env' -f '$RemoteRoot/current/deploy/azure/compose.yaml' up -d main
/usr/bin/docker compose --env-file '$RemoteRoot/shared/azure.env' -f '$RemoteRoot/current/deploy/azure/compose.yaml' up -d proxy
wait_https() {
    url="`$1"
    attempt=1
    while [ "`$attempt" -le 48 ]; do
        if curl --fail --silent --show-error --max-time 8 "`$url" >/dev/null; then
            return 0
        fi
        sleep 5
        attempt=`$((attempt + 1))
    done
    echo "health endpoint did not become ready: `$url" >&2
    return 1
}
AZURE_FQDN=`$(sed -n 's/^AZURE_FQDN=//p' '$RemoteRoot/shared/azure.env' | head -n 1)
test -n "`$AZURE_FQDN"
wait_https "https://`$AZURE_FQDN/health"
wait_https "https://`${AZURE_FQDN}:8443/health"
wait_https "https://`${AZURE_FQDN}:9443/health"
wait_https "https://`${AZURE_FQDN}:9443/static/index.html"
if ! curl --fail --silent --show-error --max-time 8 -I "http://`${AZURE_FQDN}/" | grep -Eq '^HTTP/[^ ]+ (301|302|307|308) '; then
    echo 'HTTP port 80 did not return a safe redirect.' >&2
    exit 1
fi
sudo install -m 0644 '$RemoteRoot/current/deploy/azure/systemd/ai-tryon-course.service' /etc/systemd/system/ai-tryon-course.service
sudo systemctl daemon-reload
sudo systemctl enable ai-tryon-course.service
sudo systemctl restart ai-tryon-course.service
wait_https "https://`$AZURE_FQDN/health"
wait_https "https://`${AZURE_FQDN}:8443/health"
wait_https "https://`${AZURE_FQDN}:9443/health"
"@
Invoke-CheckedNative -CommandName 'ssh' -ArgumentList @('-i', $privateKeyPath, '-o', 'BatchMode=yes', $remote, $remoteScript) -Context 'verify checksum, build sequentially, and start the release stack' | Out-Null
Write-Output "deployed release archive: $archiveName"
Write-Output "release id: $releaseId"
Write-Output 'production environment transferred with remote mode 0600; its contents were not printed.'
