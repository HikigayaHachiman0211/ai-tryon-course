[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidatePattern('^[a-zA-Z0-9.-]+$')][string]$AzureFqdn,
    [Parameter(Mandatory = $false)][int]$TimeoutSeconds = 20,
    [Parameter(Mandatory = $false)][string]$EvidencePath
)

. (Join-Path $PSScriptRoot 'common.ps1')

$checks = @(
    @{ name = 'main-health'; uri = "https://$AzureFqdn/health" },
    @{ name = 'main-deep-health'; uri = "https://$AzureFqdn/health/deep" },
    @{ name = 'admin-health'; uri = "https://$AzureFqdn`:8443/health" },
    @{ name = 'admin-deep-health'; uri = "https://$AzureFqdn`:8443/health/deep" },
    @{ name = 'workbench-health'; uri = "https://$AzureFqdn`:9443/health" },
    @{ name = 'workbench-entry'; uri = "https://$AzureFqdn`:9443/static/index.html" }
)
$results = @()
foreach ($check in $checks) {
    $started = Get-Date
    try {
        $response = Invoke-WebRequest -Uri $check.uri -UseBasicParsing -TimeoutSec $TimeoutSeconds
        $elapsed = ((Get-Date) - $started).TotalMilliseconds
        if ($response.StatusCode -lt 200 -or $response.StatusCode -ge 400) { throw "HTTP $($response.StatusCode)" }
        $results += [pscustomobject]@{ name = $check.name; status = [int]$response.StatusCode; durationMs = [math]::Round($elapsed, 1); ok = $true }
        Write-Output "$($check.name): HTTP $($response.StatusCode) $([math]::Round($elapsed, 1))ms"
    } catch {
        $results += [pscustomobject]@{ name = $check.name; status = 0; durationMs = 0; ok = $false }
        throw "Smoke check failed for $($check.uri): $($_.Exception.Message)"
    }
}

$redirectStatus = $null
try {
    $redirect = Invoke-WebRequest -Uri "http://$AzureFqdn/" -UseBasicParsing -MaximumRedirection 0 -TimeoutSec $TimeoutSeconds -ErrorAction Stop
    $redirectStatus = [int]$redirect.StatusCode
} catch {
    $redirectResponse = $_.Exception.Response
    if ($null -ne $redirectResponse -and $null -ne $redirectResponse.StatusCode) {
        $redirectStatus = [int]$redirectResponse.StatusCode
    } else {
        throw "HTTP port 80 request failed before a redirect response: $($_.Exception.Message)"
    }
}
if ($redirectStatus -notin @(301, 302, 307, 308)) { throw "HTTP port 80 did not redirect safely; status was $redirectStatus" }
Write-Output "http-redirect: HTTP $redirectStatus"

if ($EvidencePath) {
    $evidenceDirectory = Split-Path -Parent $EvidencePath
    New-Item -ItemType Directory -Path $evidenceDirectory -Force | Out-Null
    [ordered]@{ fqdn = $AzureFqdn; checks = $results; httpRedirect = $redirectStatus } | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $EvidencePath -Encoding utf8
    Write-Output "sanitized smoke evidence: $EvidencePath"
}
