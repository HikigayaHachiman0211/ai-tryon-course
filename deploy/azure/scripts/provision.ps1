[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-fA-F-]{36}$')][string]$AzureSubscriptionId,
    [Parameter(Mandatory = $true)][string]$AzureLocation,
    [Parameter(Mandatory = $true)][string]$AzureResourceGroup,
    [Parameter(Mandatory = $true)][ValidatePattern('^[a-z0-9-]{3,63}$')][string]$DnsLabel,
    [Parameter(Mandatory = $true)][ValidatePattern('^[a-z0-9]{3,24}$')][string]$StorageAccountName,
    [Parameter(Mandatory = $true)][string]$AdminUsername,
    [Parameter(Mandatory = $true)][string]$SshPublicKeyPath,
    [Parameter(Mandatory = $true)][string]$BudgetAlertEmail,
    [Parameter(Mandatory = $true)][datetime]$StudentCreditExpiryDate,
    [Parameter(Mandatory = $true)][ValidateRange(0.01, 100000)][decimal]$EstimatedMonthlyCostUsd,
    [Parameter(Mandatory = $true)][ValidateRange(0, 100000)][decimal]$RemainingCreditUsd,
    [Parameter(Mandatory = $true)][switch]$ConfirmAzureForStudents,
    [Parameter(Mandatory = $true)][switch]$ConfirmWhatIf,
    [Parameter(Mandatory = $false)][string]$ExpectedStudentSubscriptionId,
    [Parameter(Mandatory = $false)][ValidateSet('Standard_B2als_v2', 'Standard_B2s')][string]$VmSize = 'Standard_B2als_v2',
    [Parameter(Mandatory = $false)][decimal]$MaxEstimatedMonthlyCostUsd = 25,
    [Parameter(Mandatory = $false)][decimal]$MinRemainingCreditReserveUsd = 20,
    [Parameter(Mandatory = $false)][string]$SshSourceCidr,
    [Parameter(Mandatory = $false)][string]$AdminTagsJson = '{"project":"ai-tryon-course","managedBy":"azure-bicep","environment":"course-demo"}'
)

. (Join-Path $PSScriptRoot 'common.ps1')

$repositoryRoot = Get-RepositoryRoot
$infraRoot = Join-Path $repositoryRoot 'deploy\azure\infra'
$exampleParametersPath = Join-Path $infraRoot 'main.parameters.example.json'
$generatedParametersPath = Join-Path $infraRoot 'main.parameters.json'
$sshKeyPath = (Resolve-Path -LiteralPath $SshPublicKeyPath).Path
$sshPublicKey = (Get-Content -LiteralPath $sshKeyPath -Raw).Trim()
if ($sshPublicKey -notmatch '^ssh-(rsa|ed25519|ecdsa)\s+') { throw 'SshPublicKeyPath must contain an OpenSSH public key, not a private key.' }
if ($sshPublicKey -match 'PRIVATE KEY') { throw 'Private SSH keys are not accepted.' }
if (-not $SshSourceCidr) {
    $resolvedPublicIpv4 = (Invoke-RestMethod -Uri 'https://api.ipify.org?format=text' -TimeoutSec 15).ToString().Trim()
    [System.Net.IPAddress]::Parse($resolvedPublicIpv4) | Out-Null
    $SshSourceCidr = "$resolvedPublicIpv4/32"
}

$preflightPath = Join-Path $PSScriptRoot 'preflight.ps1'
$preflightArguments = @{
    AzureSubscriptionId = $AzureSubscriptionId
    AzureLocation = $AzureLocation
    AzureResourceGroup = $AzureResourceGroup
    DnsLabel = $DnsLabel
    StorageAccountName = $StorageAccountName
    EstimatedMonthlyCostUsd = $EstimatedMonthlyCostUsd
    RemainingCreditUsd = $RemainingCreditUsd
    BudgetAlertEmail = $BudgetAlertEmail
    StudentCreditExpiryDate = $StudentCreditExpiryDate
    ConfirmAzureForStudents = $ConfirmAzureForStudents
    ExpectedStudentSubscriptionId = $ExpectedStudentSubscriptionId
    VmSize = $VmSize
    MaxEstimatedMonthlyCostUsd = $MaxEstimatedMonthlyCostUsd
    MinRemainingCreditReserveUsd = $MinRemainingCreditReserveUsd
    SshSourceCidr = $SshSourceCidr
    EvidencePath = (Join-Path $repositoryRoot 'evidence\azure\preflight.json')
}
& $preflightPath @preflightArguments

$parameterObject = Get-Content -LiteralPath $exampleParametersPath -Raw | ConvertFrom-Json
$parameterObject.parameters.location.value = $AzureLocation
$parameterObject.parameters.namePrefix.value = 'ai-tryon-course'
$parameterObject.parameters.adminUsername.value = $AdminUsername
$parameterObject.parameters.adminSshPublicKey.value = $sshPublicKey
$parameterObject.parameters.sshSourceCidr.value = $SshSourceCidr
$parameterObject.parameters.vmSize.value = $VmSize
$parameterObject.parameters.dnsLabel.value = $DnsLabel
$parameterObject.parameters.storageAccountName.value = $StorageAccountName
$parameterObject.parameters.tags.value = ($AdminTagsJson | ConvertFrom-Json)
$parameterObject | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $generatedParametersPath -Encoding utf8
Write-Output "generated parameters: $generatedParametersPath (no secret values; SSH public key only; keep ignored)"

Invoke-CheckedNative -CommandName 'az' -ArgumentList @('group', 'create', '--name', $AzureResourceGroup, '--location', $AzureLocation, '--subscription', $AzureSubscriptionId, '--tags', 'project=ai-tryon-course', 'managedBy=azure-bicep', 'environment=course-demo', '--output', 'none') -Context 'create/select the explicitly named resource group after preflight' | Out-Null

$whatIfArguments = @(
    'deployment', 'group', 'what-if',
    '--subscription', $AzureSubscriptionId,
    '--resource-group', $AzureResourceGroup,
    '--template-file', (Join-Path $infraRoot 'main.bicep'),
    '--parameters', "@$generatedParametersPath",
    '--mode', 'Incremental',
    '--no-pretty-print'
)
Write-Output 'Bicep what-if follows. Inspect resource names, types, SKU, and changes before approving.'
Invoke-CheckedNative -CommandName 'az' -ArgumentList $whatIfArguments -Context 'inspect Bicep what-if before deployment'
if (-not $ConfirmWhatIf) {
    throw 'What-if completed. Re-run with -ConfirmWhatIf only after confirming there are no unexpected resources or destructive changes.'
}

$deploymentName = "ai-tryon-$(Get-Date -AsUTC -Format 'yyyyMMddHHmmss')"
$createArguments = @(
    'deployment', 'group', 'create',
    '--name', $deploymentName,
    '--subscription', $AzureSubscriptionId,
    '--resource-group', $AzureResourceGroup,
    '--template-file', (Join-Path $infraRoot 'main.bicep'),
    '--parameters', "@$generatedParametersPath",
    '--mode', 'Incremental',
    '--output', 'none'
)
Invoke-CheckedNative -CommandName 'az' -ArgumentList $createArguments -Context 'deploy the approved low-cost Azure VM topology' | Out-Null

$outputJson = Invoke-CheckedNative -CommandName 'az' -ArgumentList @('deployment', 'group', 'show', '--name', $deploymentName, '--resource-group', $AzureResourceGroup, '--subscription', $AzureSubscriptionId, '--query', 'properties.outputs', '--output', 'json') -Context 'read non-secret deployment outputs'
$outputs = ($outputJson -join [Environment]::NewLine) | ConvertFrom-Json
Write-Output "deployment name: $deploymentName"
foreach ($outputName in @('publicIpAddress', 'fqdn', 'storageAccountName', 'sshUsername', 'vmResourceId')) {
    $property = $outputs.$outputName
    if ($property) { Write-Output "${outputName}: $($property.value)" }
}
Write-Output 'Deployment outputs exclude access keys, connection strings, private keys, API keys, and passwords.'
