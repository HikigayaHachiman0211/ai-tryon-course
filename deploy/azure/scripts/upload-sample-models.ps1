[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$StorageAccountName,
    [Parameter(Mandatory = $false)][string]$SampleDirectory,
    [Parameter(Mandatory = $false)][string]$ContainerName = 'product-assets'
)

. (Join-Path $PSScriptRoot 'common.ps1')

$repositoryRoot = Get-RepositoryRoot
if (-not $SampleDirectory) {
    $SampleDirectory = Join-Path $repositoryRoot 'main-app\frontend\public\sample-models'
}
$maleLabel = [string][char]0x7537
$femaleLabel = [string][char]0x5973
$specifications = @(
    @{ Folder = 'male'; Gender = $maleLabel; Name = 'mannequin-male-1.png' },
    @{ Folder = 'male'; Gender = $maleLabel; Name = 'mannequin-male-2.png' },
    @{ Folder = 'female'; Gender = $femaleLabel; Name = 'mannequin-female-1.png' },
    @{ Folder = 'female'; Gender = $femaleLabel; Name = 'mannequin-female-2.png' }
)

# Verify every local image before contacting Azure or uploading anything.
$items = foreach ($specification in $specifications) {
    $source = Join-Path (Join-Path $SampleDirectory $specification.Folder) $specification.Name
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Missing sample model image: $source"
    }
    [pscustomobject]@{
        Source = $source
        Name = "sample_models/$($specification.Gender)/$($specification.Name)"
        Sha256 = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
        ContentType = if ($specification.Name.EndsWith('.jpg')) { 'image/jpeg' } else { 'image/webp' }
    }
}

$missing = @()
foreach ($item in $items) {
    $existsJson = Invoke-CheckedNative -CommandName 'az' -ArgumentList @(
        'storage', 'blob', 'exists', '--account-name', $StorageAccountName,
        '--container-name', $ContainerName, '--name', $item.Name, '--auth-mode', 'login', '--output', 'json'
    ) -Context "check sample model object $($item.Name)" | Out-String
    if ([bool]($existsJson | ConvertFrom-Json).exists) {
        $remoteHash = (Invoke-CheckedNative -CommandName 'az' -ArgumentList @(
            'storage', 'blob', 'show', '--account-name', $StorageAccountName,
            '--container-name', $ContainerName, '--name', $item.Name, '--auth-mode', 'login',
            '--query', 'metadata.sha256', '--output', 'tsv'
        ) -Context "check sample model hash $($item.Name)" | Out-String).Trim().ToLowerInvariant()
        if ($remoteHash -ne $item.Sha256) {
            throw "Existing sample model hash differs; refusing overwrite: $($item.Name)"
        }
    } else {
        $missing += $item
    }
}

foreach ($item in $missing) {
    Invoke-CheckedNative -CommandName 'az' -ArgumentList @(
        'storage', 'blob', 'upload', '--account-name', $StorageAccountName,
        '--container-name', $ContainerName, '--name', $item.Name, '--file', $item.Source,
        '--auth-mode', 'login', '--overwrite', 'false', '--content-type', $item.ContentType,
        '--content-cache-control', 'public, max-age=31536000, immutable',
        '--metadata', "sha256=$($item.Sha256)", '--output', 'none'
    ) -Context "upload sample model $($item.Name)" | Out-Null
}
Write-Output "Sample models: $($missing.Count) uploaded, $($items.Count - $missing.Count) already verified."
