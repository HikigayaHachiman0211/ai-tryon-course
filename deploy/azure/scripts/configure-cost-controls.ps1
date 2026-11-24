[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-fA-F-]{36}$')][string]$AzureSubscriptionId,
    [Parameter(Mandatory = $true)][ValidatePattern('^[a-z0-9-]{3,40}$')][string]$NamePrefix,
    [Parameter(Mandatory = $true)][ValidateRange(0, 100000)][decimal]$RemainingCreditUsd,
    [Parameter(Mandatory = $true)][string]$BudgetAlertEmail,
    [Parameter(Mandatory = $true)][datetime]$StudentCreditExpiryDate,
    [Parameter(Mandatory = $false)][decimal]$MaxEstimatedMonthlyCostUsd = 25,
    [Parameter(Mandatory = $false)][decimal]$MinRemainingCreditReserveUsd = 20,
    [Parameter(Mandatory = $true)][switch]$ConfirmAzureForStudents
)

. (Join-Path $PSScriptRoot 'common.ps1')

if (-not $ConfirmAzureForStudents) { throw 'Confirm the exact Azure for Students subscription before changing subscription-scope cost controls.' }
Assert-ValidEmail -Email $BudgetAlertEmail
$accountJson = Invoke-CheckedNative -CommandName 'az' -ArgumentList @('account', 'show', '--subscription', $AzureSubscriptionId, '--output', 'json') -Context 'verify the exact subscription before changing cost controls' | Out-String
$account = $accountJson | ConvertFrom-Json
if ($account.state -ne 'Enabled' -or $account.id.ToLowerInvariant() -ne $AzureSubscriptionId.ToLowerInvariant()) { throw 'The selected Azure subscription is not enabled or does not match the requested ID.' }
$budgetAmount = [Math]::Min($MaxEstimatedMonthlyCostUsd, ($RemainingCreditUsd - $MinRemainingCreditReserveUsd))
if ($budgetAmount -le 0) { throw 'The computed budget is nonpositive; refusing to create a budget.' }
if ($StudentCreditExpiryDate.ToUniversalTime() -le [datetime]::UtcNow) { throw 'StudentCreditExpiryDate must be in the future.' }

$consumptionState = Invoke-CheckedNative -CommandName 'az' -ArgumentList @('provider', 'show', '--subscription', $AzureSubscriptionId, '--namespace', 'Microsoft.Consumption', '--output', 'json') -Context 'check cost-management provider' | Out-String
$consumption = $consumptionState | ConvertFrom-Json
if ($consumption.registrationState -ne 'Registered') {
    Invoke-CheckedNative -CommandName 'az' -ArgumentList @('provider', 'register', '--subscription', $AzureSubscriptionId, '--namespace', 'Microsoft.Consumption', '--wait') -Context 'register Microsoft.Consumption only when required' | Out-Null
}

$budgetName = "$NamePrefix-monthly"
$startDate = (Get-Date -Day 1).ToUniversalTime().ToString('yyyy-MM-dd')
$endDate = $StudentCreditExpiryDate.ToUniversalTime().ToString('yyyy-MM-dd')
$notifications = [ordered]@{}
foreach ($threshold in @(50, 75, 90, 100)) {
    $notifications["Actual_GreaterThan_${threshold}_Percent"] = [ordered]@{
        enabled = $true
        operator = 'GreaterThan'
        threshold = $threshold
        contactEmails = @($BudgetAlertEmail)
        contactRoles = @()
        contactGroups = @()
    }
}
$notificationJson = $notifications | ConvertTo-Json -Depth 8 -Compress

try {
    Invoke-CheckedNative -CommandName 'az' -ArgumentList @(
        'consumption', 'budget', 'create',
        '--subscription', $AzureSubscriptionId,
        '--budget-name', $budgetName,
        '--amount', ([string]$budgetAmount),
        '--time-grain', 'Monthly',
        '--start-date', $startDate,
        '--end-date', $endDate,
        '--category', 'Cost',
        '--notifications', $notificationJson,
        '--output', 'none'
    ) -Context 'create/update subscription monthly cost budget' | Out-Null
} catch {
    throw "Azure rejected the API-created budget. Do not claim it exists. Use the Portal fallback in deploy/azure/README.md and record human confirmation. Details: $($_.Exception.Message)"
}

$budgetJson = Invoke-CheckedNative -CommandName 'az' -ArgumentList @('consumption', 'budget', 'show', '--subscription', $AzureSubscriptionId, '--budget-name', $budgetName, '--output', 'json') -Context 'verify created cost budget' | Out-String
$budget = $budgetJson | ConvertFrom-Json
if ([decimal]$budget.amount -ne [decimal]$budgetAmount) { throw 'Verified budget amount differs from the guarded amount.' }
Write-Output "budget name: $budgetName"
Write-Output "budget scope: /subscriptions/$(Get-SafeIdentifier -Value $AzureSubscriptionId)"
Write-Output "budget amount: USD $budgetAmount monthly"
Write-Output 'notifications: actual cost thresholds 50%, 75%, 90%, 100% (email address intentionally omitted)'
Write-Output 'budgets notify; they do not automatically stop resources.'
