[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-fA-F-]{36}$')][string]$AzureSubscriptionId,
    [Parameter(Mandatory = $true)][string]$AzureLocation,
    [Parameter(Mandatory = $true)][string]$AzureResourceGroup,
    [Parameter(Mandatory = $true)][ValidatePattern('^[a-z0-9-]{3,63}$')][string]$DnsLabel,
    [Parameter(Mandatory = $true)][ValidatePattern('^[a-z0-9]{3,24}$')][string]$StorageAccountName,
    [Parameter(Mandatory = $true)][ValidateRange(0.01, 100000)][decimal]$EstimatedMonthlyCostUsd,
    [Parameter(Mandatory = $true)][ValidateRange(0, 100000)][decimal]$RemainingCreditUsd,
    [Parameter(Mandatory = $true)][string]$BudgetAlertEmail,
    [Parameter(Mandatory = $true)][datetime]$StudentCreditExpiryDate,
    [Parameter(Mandatory = $true)][switch]$ConfirmAzureForStudents,
    [Parameter(Mandatory = $false)][string]$ExpectedStudentSubscriptionId,
    [Parameter(Mandatory = $false)][decimal]$MaxEstimatedMonthlyCostUsd = 25,
    [Parameter(Mandatory = $false)][decimal]$MinRemainingCreditReserveUsd = 20,
    [Parameter(Mandatory = $false)][ValidateSet('Standard_B2als_v2', 'Standard_B2s')][string]$VmSize = 'Standard_B2als_v2',
    [Parameter(Mandatory = $false)][string]$SshSourceCidr,
    [Parameter(Mandatory = $false)][string]$EvidencePath
)

. (Join-Path $PSScriptRoot 'common.ps1')

if (-not $ConfirmAzureForStudents) {
    throw 'Pass -ConfirmAzureForStudents only after confirming the exact ID in the Portal subscription blade and Sponsorships portal.'
}
Assert-ValidEmail -Email $BudgetAlertEmail
if ($StudentCreditExpiryDate.ToUniversalTime() -le [datetime]::UtcNow) {
    throw 'StudentCreditExpiryDate must be in the future.'
}
if ($ExpectedStudentSubscriptionId -and $ExpectedStudentSubscriptionId.ToLowerInvariant() -ne $AzureSubscriptionId.ToLowerInvariant()) {
    throw 'AzureSubscriptionId does not match the exact student signup subscription ID supplied outside Git.'
}
if ($EstimatedMonthlyCostUsd -gt $MaxEstimatedMonthlyCostUsd) {
    throw "Estimated monthly cost exceeds the USD $MaxEstimatedMonthlyCostUsd guard. Obtain explicit threshold approval before continuing."
}
if ($RemainingCreditUsd - $EstimatedMonthlyCostUsd -lt $MinRemainingCreditReserveUsd) {
    throw "Estimated deployment would reduce remaining credit below the USD $MinRemainingCreditReserveUsd reserve."
}

$requiredCommands = @{
    az = @('az')
    bicep = @('az')
    docker = @('docker')
    node = @('node')
    npm = @('npm')
    python = @('python', 'python3')
    ssh = @('ssh', 'ssh.exe')
    scp = @('scp', 'scp.exe')
    curl = @('curl.exe', 'curl')
}
foreach ($toolName in $requiredCommands.Keys) {
    $resolvedTool = Test-CheckedCommand -CommandCandidates $requiredCommands[$toolName]
    if (-not $resolvedTool) { throw "Required tool is missing: $toolName" }
    Write-Output "tool ${toolName}: available"
}
if (Test-CheckedCommand -CommandCandidates @('azcopy')) {
    Write-Output 'tool azcopy: optional available (Azure CLI upload path remains the default)'
} else {
    Write-Output 'tool azcopy: optional not installed; Azure CLI upload path will be used'
}
Invoke-CheckedNative -CommandName 'az' -ArgumentList @('bicep', 'version') -Context 'verify Bicep CLI' | Out-Null
Invoke-CheckedNative -CommandName 'docker' -ArgumentList @('compose', 'version') -Context 'verify Docker Compose plugin' | Out-Null

$accountJson = Invoke-CheckedNative -CommandName 'az' -ArgumentList @('account', 'show', '--subscription', $AzureSubscriptionId, '--output', 'json') -Context 'read explicitly selected Azure subscription'
$account = ($accountJson -join [Environment]::NewLine) | ConvertFrom-Json
if ($account.state -ne 'Enabled') { throw "Selected subscription is not Enabled: $account.state" }
if ($account.id.ToLowerInvariant() -ne $AzureSubscriptionId.ToLowerInvariant()) { throw 'Azure CLI returned a different subscription ID.' }

$safeSubscriptionId = Get-SafeIdentifier -Value $AzureSubscriptionId
Write-Output "subscription name: $($account.name)"
Write-Output "subscription id: $safeSubscriptionId"
Write-Output "tenant id: $(Get-SafeIdentifier -Value ([string]$account.tenantId))"
Write-Output "subscription state: $($account.state)"
Write-Output 'Azure for Students evidence: operator-confirmed from signup record, Portal subscription blade, and Sponsorships portal; not machine-proven by the mutable CLI display name.'

foreach ($providerNamespace in @('Microsoft.Compute', 'Microsoft.Network', 'Microsoft.Storage')) {
    $providerJson = Invoke-CheckedNative -CommandName 'az' -ArgumentList @('provider', 'show', '--subscription', $AzureSubscriptionId, '--namespace', $providerNamespace, '--output', 'json') -Context "check $providerNamespace registration in selected subscription"
    $provider = ($providerJson -join [Environment]::NewLine) | ConvertFrom-Json
    if ($provider.registrationState -ne 'Registered') {
        Write-Output "registering in-scope provider $providerNamespace"
        Invoke-CheckedNative -CommandName 'az' -ArgumentList @('provider', 'register', '--subscription', $AzureSubscriptionId, '--namespace', $providerNamespace, '--wait') -Context "register $providerNamespace in selected subscription" | Out-Null
    }
}

if (-not $SshSourceCidr) {
    try {
        $resolvedPublicIpv4 = (Invoke-RestMethod -Uri 'https://api.ipify.org?format=text' -TimeoutSec 15).ToString().Trim()
        [System.Net.IPAddress]::Parse($resolvedPublicIpv4) | Out-Null
        $SshSourceCidr = "$resolvedPublicIpv4/32"
    } catch {
        throw 'Could not resolve the operator public IPv4; refusing a globally open SSH rule.'
    }
}
[System.Net.IPAddress]$sshAddress = $null
if ($SshSourceCidr -notmatch '^([^/]+)/32$' -or -not [System.Net.IPAddress]::TryParse($matches[1], [ref]$sshAddress) -or $sshAddress.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) {
    throw 'SshSourceCidr must be the operator public IPv4 with an exact /32 mask.'
}
Write-Output "SSH source CIDR: $SshSourceCidr"

$skuJson = Invoke-CheckedNative -CommandName 'az' -ArgumentList @('vm', 'list-skus', '--location', $AzureLocation, '--size', $VmSize, '--all', '--output', 'json') -Context "verify selected AMD64 VM SKU $VmSize"
$skuItems = @(($skuJson -join [Environment]::NewLine) | ConvertFrom-Json)
if ($skuItems.Count -eq 0) { throw "$VmSize was not returned for the selected region. Re-run with the approved Standard_B2s fallback if Standard_B2als_v2 is unavailable." }
if (@($skuItems | Where-Object { @($_.restrictions).Count -gt 0 }).Count -gt 0) { throw "$VmSize has Azure restrictions in the selected region. Re-run with the approved Standard_B2s fallback if Standard_B2als_v2 is unavailable." }
$architectureValues = @($skuItems | ForEach-Object { @($_.capabilities) } | Where-Object { $_.name -eq 'CpuArchitectureType' } | ForEach-Object { $_.value })
if ($architectureValues.Count -gt 0 -and ($architectureValues -notcontains 'AMD64')) { throw "$VmSize is not reported as AMD64 in the selected region." }
Write-Output "VM SKU: $VmSize (AMD64 check passed or Azure omitted the capability field)"

$usageJson = Invoke-CheckedNative -CommandName 'az' -ArgumentList @('vm', 'list-usage', '--location', $AzureLocation, '--output', 'json') -Context 'verify regional vCPU quota'
$usageItems = @(($usageJson -join [Environment]::NewLine) | ConvertFrom-Json)
$coreUsage = $usageItems | Where-Object { [string]$_.name.value -match 'cores|vCPU' } | Select-Object -First 1
if (-not $coreUsage -or [decimal]$coreUsage.currentValue -ge [decimal]$coreUsage.limit) { throw 'Regional vCPU quota is unavailable or exhausted.' }
Write-Output "vCPU quota: $($coreUsage.currentValue)/$($coreUsage.limit)"

$dnsJson = Invoke-CheckedNative -CommandName 'az' -ArgumentList @('network', 'public-ip', 'check-dns-name', '--name', $DnsLabel, '--location', $AzureLocation, '--output', 'json') -Context 'check Azure DNS label availability'
$dnsCheck = ($dnsJson -join [Environment]::NewLine) | ConvertFrom-Json
if (-not $dnsCheck.nameAvailable) { throw "DNS label is unavailable: $DnsLabel" }
$storageJson = Invoke-CheckedNative -CommandName 'az' -ArgumentList @('storage', 'account', 'check-name', '--name', $StorageAccountName, '--output', 'json') -Context 'check storage account name availability'
$storageCheck = ($storageJson -join [Environment]::NewLine) | ConvertFrom-Json
if (-not $storageCheck.nameAvailable) { throw "Storage account name is unavailable: $StorageAccountName" }

# Query the current regional retail catalog as an evidence check. The
# conservative total is still supplied by the operator because image/AI/API
# usage cannot be inferred safely from a static SKU query.
$priceFilter = [uri]::EscapeDataString("armRegionName eq '$AzureLocation' and priceType eq 'Consumption'")
$priceUri = "https://prices.azure.com/api/retail/prices?`$filter=$priceFilter"
$priceResponse = Invoke-RestMethod -Uri $priceUri -TimeoutSec 45
$priceCount = @($priceResponse.Items).Count
if ($priceCount -eq 0) { throw 'Azure Retail Prices API returned no regional consumption records; refusing to treat the estimate as verified.' }
Write-Output "retail price evidence: $priceCount regional consumption records queried"
Write-Output "conservative 30-day estimate: USD $EstimatedMonthlyCostUsd"
Write-Output "remaining credit after estimate: USD $($RemainingCreditUsd - $EstimatedMonthlyCostUsd)"
Write-Output 'free-service eligibility and actual invoice treatment may differ from retail estimates.'
Write-Output 'preflight passed without creating Azure resources.'

if ($EvidencePath) {
    $evidenceDirectory = Split-Path -Parent $EvidencePath
    New-Item -ItemType Directory -Path $evidenceDirectory -Force | Out-Null
    [ordered]@{
        subscription = $safeSubscriptionId
        tenant = Get-SafeIdentifier -Value ([string]$account.tenantId)
        subscriptionState = $account.state
        region = $AzureLocation
        resourceGroup = $AzureResourceGroup
        sshSourceCidr = $SshSourceCidr
        vmSku = $VmSize
        retailRecordCount = $priceCount
        estimatedMonthlyCostUsd = [decimal]$EstimatedMonthlyCostUsd
        remainingCreditAfterEstimateUsd = [decimal]($RemainingCreditUsd - $EstimatedMonthlyCostUsd)
        azureForStudentsOperatorConfirmed = $true
        budgetEmailRecordedOutsideGit = $true
        studentCreditExpiryDate = $StudentCreditExpiryDate.ToUniversalTime().ToString('o')
    } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $EvidencePath -Encoding utf8
    Write-Output "sanitized evidence: $EvidencePath (no email or secret values)"
}
