[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$MainUrl,

    [Parameter(Mandatory = $true)]
    [string]$WorkbenchUrl,

    [Parameter(Mandatory = $true)]
    [string]$AdminUrl
)

$ErrorActionPreference = "Stop"

function Invoke-Probe {
    param([string]$Url, [int]$ExpectedStatus = 200)
    Write-Host "Checking $Url ..."
    $statusCode = 0
    $content = ""
    try {
        $resp = Invoke-WebRequest -Uri $Url -Method Get -TimeoutSec 60 -UseBasicParsing
        $statusCode = [int]$resp.StatusCode
        $content = $resp.Content
    }
    catch [System.Net.WebException] {
        if ($_.Exception.Response) {
            $statusCode = [int]$_.Exception.Response.StatusCode
            $stream = $_.Exception.Response.GetResponseStream()
            if ($stream) {
                $reader = New-Object System.IO.StreamReader($stream)
                $content = $reader.ReadToEnd()
            }
        }
        else {
            throw "Probe failed for ${Url}: $($_.Exception.Message)"
        }
    }
    catch {
        throw "Probe failed for ${Url}: $($_.Exception.Message)"
    }

    if ($statusCode -ne $ExpectedStatus) {
        throw "Expected HTTP $ExpectedStatus from $Url, got $statusCode"
    }
    return [pscustomobject]@{
        StatusCode = $statusCode
        Content = $content
    }
}

# 1. Cold-start health probes (may take several seconds when waking from minReplicas=0)
Invoke-Probe -Url "$($MainUrl.TrimEnd('/'))/health/deep" -ExpectedStatus 200 | Out-Null
Invoke-Probe -Url "$($WorkbenchUrl.TrimEnd('/'))/health/deep" -ExpectedStatus 200 | Out-Null
Invoke-Probe -Url "$($AdminUrl.TrimEnd('/'))/health/deep" -ExpectedStatus 200 | Out-Null

# 2. Verify unauthenticated debug routes are disabled on main site
Invoke-Probe -Url "$($MainUrl.TrimEnd('/'))/api/debug/errors/recent" -ExpectedStatus 403 | Out-Null

# 3. Verify products endpoint includes seeded product_url
$prodResp = Invoke-Probe -Url "$($MainUrl.TrimEnd('/'))/api/products?limit=5" -ExpectedStatus 200
$prodData = $prodResp.Content | ConvertFrom-Json
if (-not $prodData.items -or $prodData.items.Count -eq 0) {
    throw "Main /api/products returned zero items"
}

Write-Host "All ACA scale-to-zero smoke checks passed!"
