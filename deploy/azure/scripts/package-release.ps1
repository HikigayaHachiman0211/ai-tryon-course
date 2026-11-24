[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)][string]$OutputRoot,
    [Parameter(Mandatory = $false)][string]$ReleaseId,
    [Parameter(Mandatory = $false)][switch]$BuildImages
)

. (Join-Path $PSScriptRoot 'common.ps1')

$repositoryRoot = Get-RepositoryRoot
if (-not $OutputRoot) { $OutputRoot = Join-Path $repositoryRoot 'deploy\azure\releases' }
$resolvedOutputRoot = [System.IO.Path]::GetFullPath($OutputRoot)
$testEnvPath = Join-Path $repositoryRoot 'deploy\azure\.env.azure.test'
if (-not (Test-Path -LiteralPath $testEnvPath)) {
    & (Join-Path $PSScriptRoot 'render-local-test-env.ps1')
}

$helperPath = Join-Path $repositoryRoot 'scripts\release\build_release.py'
$arguments = @($helperPath, '--root', $repositoryRoot, '--output-root', $resolvedOutputRoot)
if ($ReleaseId) { $arguments += @('--release-id', $ReleaseId) }
$releaseOutput = Invoke-CheckedNative -CommandName 'python' -ArgumentList $arguments -Context 'create clean-room release package'
$releaseInfo = ($releaseOutput -join [Environment]::NewLine) | ConvertFrom-Json
$releaseDirectory = [string]$releaseInfo.release_directory
$composeFile = Join-Path $releaseDirectory 'deploy\azure\compose.yaml'

$oldReleaseId = [Environment]::GetEnvironmentVariable('RELEASE_ID', 'Process')
$oldImageNamespace = [Environment]::GetEnvironmentVariable('IMAGE_NAMESPACE', 'Process')
$oldComposeParallelLimit = [Environment]::GetEnvironmentVariable('COMPOSE_PARALLEL_LIMIT', 'Process')
try {
    $env:RELEASE_ID = [string]$releaseInfo.release_id
    $env:IMAGE_NAMESPACE = 'local/ai-tryon-course'
    $env:COMPOSE_PARALLEL_LIMIT = '1'
    Invoke-CheckedNative -CommandName 'docker' -ArgumentList @('compose', '--env-file', $testEnvPath, '-f', $composeFile, 'config', '--quiet') -Context 'validate release Compose configuration' | Out-Null
    if ($BuildImages) {
        foreach ($serviceName in @('main', 'admin', 'workbench')) {
            Write-Output "building release image sequentially: $serviceName"
            Invoke-CheckedNative -CommandName 'docker' -ArgumentList @('compose', '--env-file', $testEnvPath, '-f', $composeFile, 'build', '--progress', 'plain', $serviceName) -Context "build clean-room $serviceName image" | Out-Null
        }
    }
} finally {
    if ($null -eq $oldReleaseId) { Remove-Item Env:RELEASE_ID -ErrorAction SilentlyContinue } else { $env:RELEASE_ID = $oldReleaseId }
    if ($null -eq $oldImageNamespace) { Remove-Item Env:IMAGE_NAMESPACE -ErrorAction SilentlyContinue } else { $env:IMAGE_NAMESPACE = $oldImageNamespace }
    if ($null -eq $oldComposeParallelLimit) { Remove-Item Env:COMPOSE_PARALLEL_LIMIT -ErrorAction SilentlyContinue } else { $env:COMPOSE_PARALLEL_LIMIT = $oldComposeParallelLimit }
}

Write-Output "release id: $($releaseInfo.release_id)"
Write-Output "release directory: $releaseDirectory"
Write-Output "release archive: $($releaseInfo.archive)"
Write-Output "archive sha256: $($releaseInfo.archive_sha256)"
Write-Output "source archive sha256: $($releaseInfo.source_archive_sha256)"
Write-Output 'release manifest includes ignored catalog/read-model assets and excludes secrets/user data.'
