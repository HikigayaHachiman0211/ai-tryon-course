[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)][switch]$BuildImages
)

. (Join-Path $PSScriptRoot '..\deploy\azure\scripts\common.ps1')

$repositoryRoot = Get-RepositoryRoot

function Invoke-InRepositoryDirectory {
    param(
        [Parameter(Mandatory = $true)][string]$RelativeDirectory,
        [Parameter(Mandatory = $true)][string]$CommandName,
        [Parameter(Mandatory = $false)][string[]]$ArgumentList = @(),
        [Parameter(Mandatory = $true)][string]$Context
    )

    $directory = (Resolve-Path -LiteralPath (Join-Path $repositoryRoot $RelativeDirectory)).Path
    Push-Location $directory
    try {
        Invoke-CheckedNative -CommandName $CommandName -ArgumentList $ArgumentList -Context $Context | Out-Null
    } finally {
        Pop-Location
    }
}

Write-Output 'running root locale and catalog gates'
Invoke-InRepositoryDirectory -RelativeDirectory '.' -CommandName 'node' -ArgumentList @('scripts/i18n/check_resource_parity.mjs') -Context 'check Main/Admin locale resource parity'
Invoke-InRepositoryDirectory -RelativeDirectory '.' -CommandName 'node' -ArgumentList @('scripts/i18n/check_resource_parity.mjs', '--admin') -Context 'check Admin locale resource parity'
Invoke-InRepositoryDirectory -RelativeDirectory '.' -CommandName 'node' -ArgumentList @('scripts/i18n/check_visible_literals.mjs', '--strict', '--all') -Context 'check visible locale literals'
Invoke-InRepositoryDirectory -RelativeDirectory '.' -CommandName 'python' -ArgumentList @('scripts/i18n/check_catalog_coverage.py') -Context 'check catalog translation coverage'
Invoke-InRepositoryDirectory -RelativeDirectory '.' -CommandName 'python' -ArgumentList @('scripts/i18n/sync_workbench_catalog.py', '--verify') -Context 'check Workbench catalog synchronization'

Write-Output 'running Main frontend gates'
Invoke-InRepositoryDirectory -RelativeDirectory 'main-app/frontend' -CommandName 'npm' -ArgumentList @('ci', '--no-audit', '--no-fund') -Context 'install Main frontend lockfile dependencies'
Invoke-InRepositoryDirectory -RelativeDirectory 'main-app/frontend' -CommandName 'npm' -ArgumentList @('run', 'lint') -Context 'lint Main frontend'
Invoke-InRepositoryDirectory -RelativeDirectory 'main-app/frontend' -CommandName 'npm' -ArgumentList @('run', 'i18n-check') -Context 'check Main frontend locale resources'
Invoke-InRepositoryDirectory -RelativeDirectory 'main-app/frontend' -CommandName 'npm' -ArgumentList @('test', '--', '--run') -Context 'test Main frontend'
Invoke-InRepositoryDirectory -RelativeDirectory 'main-app/frontend' -CommandName 'npm' -ArgumentList @('run', 'build') -Context 'build Main frontend'

Write-Output 'running Main and Admin backend gates'
Invoke-InRepositoryDirectory -RelativeDirectory 'main-app/backend' -CommandName 'python' -ArgumentList @('-m', 'pytest', 'app/tests', '-q') -Context 'test Main backend'
Invoke-InRepositoryDirectory -RelativeDirectory 'main-app/backend' -CommandName 'python' -ArgumentList @('-m', 'compileall', '-q', 'app') -Context 'compile Main backend'
Invoke-InRepositoryDirectory -RelativeDirectory 'main-app/admin/frontend' -CommandName 'npm' -ArgumentList @('ci', '--no-audit', '--no-fund') -Context 'install Admin frontend lockfile dependencies'
Invoke-InRepositoryDirectory -RelativeDirectory 'main-app/admin/frontend' -CommandName 'npm' -ArgumentList @('run', 'i18n-check') -Context 'check Admin frontend locale resources'
Invoke-InRepositoryDirectory -RelativeDirectory 'main-app/admin/frontend' -CommandName 'npm' -ArgumentList @('test', '--', '--run') -Context 'test Admin frontend'
Invoke-InRepositoryDirectory -RelativeDirectory 'main-app/admin/frontend' -CommandName 'npm' -ArgumentList @('run', 'build') -Context 'build Admin frontend'
Invoke-InRepositoryDirectory -RelativeDirectory 'main-app/admin/backend' -CommandName 'python' -ArgumentList @('-m', 'pytest', '-q') -Context 'test Admin backend'
Invoke-InRepositoryDirectory -RelativeDirectory 'main-app/admin/backend' -CommandName 'python' -ArgumentList @('-m', 'compileall', '-q', 'app') -Context 'compile Admin backend'

Write-Output 'running Workbench gates'
Invoke-InRepositoryDirectory -RelativeDirectory 'tryon-workbench' -CommandName 'npm' -ArgumentList @('ci', '--no-audit', '--no-fund') -Context 'install Workbench lockfile dependencies'
Invoke-InRepositoryDirectory -RelativeDirectory 'tryon-workbench' -CommandName 'npm' -ArgumentList @('test') -Context 'test Workbench bridge contracts'
Invoke-InRepositoryDirectory -RelativeDirectory 'tryon-workbench' -CommandName 'python' -ArgumentList @('-m', 'pytest', '-q') -Context 'test Workbench backend and SSRF guards'
Invoke-InRepositoryDirectory -RelativeDirectory 'tryon-workbench' -CommandName 'python' -ArgumentList @('-m', 'compileall', '-q', '.') -Context 'compile Workbench'

Write-Output 'running clean release package and Compose config gate'
$packageScript = Join-Path $repositoryRoot 'deploy\azure\scripts\package-release.ps1'
if ($BuildImages) {
    & $packageScript -BuildImages
} else {
    & $packageScript
}
if ($LASTEXITCODE -ne 0) { throw 'package-release.ps1 returned a nonzero exit code.' }
Write-Output 'Azure local gates passed; live Azure provisioning and acceptance remain separate.'
