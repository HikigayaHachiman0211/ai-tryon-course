[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-fA-F-]{36}$')][string]$AzureSubscriptionId,
    [Parameter(Mandatory = $true)][string]$AzureResourceGroup,
    [Parameter(Mandatory = $true)][string]$VmName,
    [Parameter(Mandatory = $true)][string]$AzureFqdn,
    [Parameter(Mandatory = $false)][string]$SshHost,
    [Parameter(Mandatory = $false)][string]$SshUsername,
    [Parameter(Mandatory = $false)][string]$SshPrivateKeyPath
)

. (Join-Path $PSScriptRoot 'common.ps1')

$vmJson = Invoke-CheckedNative -CommandName 'az' -ArgumentList @('vm', 'show', '--subscription', $AzureSubscriptionId, '--resource-group', $AzureResourceGroup, '--name', $VmName, '--show-details', '--query', '{powerState:powerState,vmSize:hardwareProfile.vmSize,publicIps:publicIps,fqdns:fqdns}', '--output', 'json') -Context 'read VM status without secrets' | Out-String
$vm = $vmJson | ConvertFrom-Json
Write-Output "subscription: $(Get-SafeIdentifier -Value $AzureSubscriptionId)"
Write-Output "VM power state: $($vm.powerState)"
Write-Output "VM size: $($vm.vmSize)"
Write-Output "public endpoint: $AzureFqdn"

foreach ($endpoint in @(
    @{ name = 'Main'; uri = "https://$AzureFqdn/health" },
    @{ name = 'Admin'; uri = "https://$AzureFqdn`:8443/health" },
    @{ name = 'Workbench'; uri = "https://$AzureFqdn`:9443/health" }
)) {
    try {
        $response = Invoke-WebRequest -Uri $endpoint.uri -UseBasicParsing -TimeoutSec 15
        Write-Output "$($endpoint.name) endpoint: HTTP $($response.StatusCode)"
    } catch {
        Write-Output "$($endpoint.name) endpoint: unavailable (diagnose with smoke-test.ps1)"
    }
}

if ($SshHost -and $SshUsername -and $SshPrivateKeyPath) {
    $privateKeyPath = (Resolve-Path -LiteralPath $SshPrivateKeyPath).Path
    $remote = "$SshUsername@$SshHost"
    $remoteStatus = "set -eu; free -h; df -h /; echo 'backup_age_utc:'; find /opt/ai-tryon-course/backups -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\\n' 2>/dev/null | sort -nr | head -n 5; /usr/bin/docker compose --env-file /opt/ai-tryon-course/shared/azure.env -f /opt/ai-tryon-course/current/deploy/azure/compose.yaml ps; /usr/bin/docker stats --no-stream --format '{{.Name}} {{.Status}} {{.MemUsage}}'; sudo journalctl -u ai-tryon-course.service -n 40 --no-pager"
    Invoke-CheckedNative -CommandName 'ssh' -ArgumentList @('-i', $privateKeyPath, '-o', 'BatchMode=yes', $remote, $remoteStatus) -Context 'read remote disk/RAM/Compose/recent service status without environment contents'
}
