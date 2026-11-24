[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$StorageAccountName,
    [Parameter(Mandatory = $false)][string]$StageDirectory,
    [Parameter(Mandatory = $false)][string]$ManifestPath,
    [Parameter(Mandatory = $false)][string]$ContainerName = 'product-assets',
    [Parameter(Mandatory = $false)][switch]$VerifyHttp,
    [Parameter(Mandatory = $false)][string]$PublicImageBaseUrl
)

. (Join-Path $PSScriptRoot 'common.ps1')

$repositoryRoot = Get-RepositoryRoot
if (-not $StageDirectory) { $StageDirectory = Join-Path $repositoryRoot 'deploy\azure\product-assets-staging' }
if (-not $ManifestPath) { $ManifestPath = Join-Path $StageDirectory 'product-assets.manifest.json' }
$stagePath = [System.IO.Path]::GetFullPath($StageDirectory)
$manifestFullPath = [System.IO.Path]::GetFullPath($ManifestPath)
New-Item -ItemType Directory -Path $stagePath -Force | Out-Null

$catalogHelper = Join-Path $repositoryRoot 'scripts\release\catalog_assets.py'
Invoke-CheckedNative -CommandName 'python' -ArgumentList @($catalogHelper, '--root', $repositoryRoot, '--manifest', $manifestFullPath, '--stage-dir', $stagePath) -Context 'verify and stage all 4,721 catalog image references' | Out-Null
$manifest = Get-Content -LiteralPath $manifestFullPath -Raw | ConvertFrom-Json
if ([int]$manifest.product_count -ne 4721) { throw "Catalog product count is not 4,721: $($manifest.product_count)" }
Write-Output "staged product references: $($manifest.product_count)"
Write-Output "staged unique objects: $($manifest.unique_object_count)"
Write-Output "manifest: $manifestFullPath"

$containerName = $ContainerName
foreach ($asset in @($manifest.objects)) {
    $sourcePath = Join-Path $stagePath ([string]$asset.name)
    $blobName = [string]$asset.name
    $existsJson = Invoke-CheckedNative -CommandName 'az' -ArgumentList @(
        'storage', 'blob', 'exists',
        '--account-name', $StorageAccountName,
        '--container-name', $containerName,
        '--name', $blobName,
        '--auth-mode', 'login',
        '--output', 'json'
    ) -Context "check upload cache for product object $blobName" | Out-String
    $exists = $existsJson | ConvertFrom-Json
    if ([bool]$exists.exists) {
        $existingHash = (Invoke-CheckedNative -CommandName 'az' -ArgumentList @(
            'storage', 'blob', 'show',
            '--account-name', $StorageAccountName,
            '--container-name', $containerName,
            '--name', $blobName,
            '--auth-mode', 'login',
            '--query', 'metadata.sha256',
            '--output', 'tsv'
        ) -Context "verify upload cache hash for product object $blobName" | Out-String).Trim().ToLowerInvariant()
        if ($existingHash -ne ([string]$asset.sha256).ToLowerInvariant()) {
            throw "Existing Azure Blob metadata hash differs for $blobName; refusing to overwrite a possibly wrong product object."
        }
        continue
    }
    $uploadArgs = @(
        'storage', 'blob', 'upload',
        '--account-name', $StorageAccountName,
        '--container-name', $containerName,
        '--name', $blobName,
        '--file', $sourcePath,
        '--auth-mode', 'login',
        '--overwrite', 'false',
        '--content-type', ([string]$asset.mime_type),
        '--content-cache-control', 'public, max-age=31536000, immutable',
        '--metadata', "sha256=$([string]$asset.sha256)",
        '--output', 'none'
    )
    Invoke-CheckedNative -CommandName 'az' -ArgumentList $uploadArgs -Context "upload verified product object $blobName" | Out-Null
}

$listJson = Invoke-CheckedNative -CommandName 'az' -ArgumentList @('storage', 'blob', 'list', '--account-name', $StorageAccountName, '--container-name', $containerName, '--auth-mode', 'login', '--num-results', '5', '--output', 'json') -Context 're-list uploaded product objects' | Out-String
@($listJson | ConvertFrom-Json) | Out-Null
Write-Output 'Azure Blob product-assets listing succeeded; container listing remains disabled for anonymous callers.'

if ($VerifyHttp) {
    if (-not $PublicImageBaseUrl) { throw '-PublicImageBaseUrl is required with -VerifyHttp.' }
    $urlHelper = Join-Path $repositoryRoot 'scripts\release\verify_public_urls.py'
    Invoke-CheckedNative -CommandName 'python' -ArgumentList @($urlHelper, '--manifest', $manifestFullPath, '--base-url', $PublicImageBaseUrl) -Context 'verify every catalog-referenced public image URL' | Out-Null
    Write-Output 'all catalog-referenced public image URLs passed HTTP image checks.'
}
