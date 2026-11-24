Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Invoke-CheckedNative {
    param(
        [Parameter(Mandatory = $true)][string]$CommandName,
        [Parameter(Mandatory = $false)][string[]]$ArgumentList = @(),
        [Parameter(Mandatory = $false)][string]$Context = $CommandName
    )

    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $nativeOutput = & $CommandName @ArgumentList 2>&1
        $nativeExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $prevEap
    }
    $stdoutLines = @($nativeOutput | Where-Object { $_ -isnot [System.Management.Automation.ErrorRecord] })
    $stderrLines = @($nativeOutput | Where-Object { $_ -is [System.Management.Automation.ErrorRecord] } | ForEach-Object { $_.ToString() })
    if ($nativeExitCode -ne 0) {
        $detail = ($stderrLines -join "`n").Trim()
        if ($detail) {
            throw "Native command failed: $CommandName (exit $nativeExitCode). Context: $Context. Details: $detail"
        }
        throw "Native command failed: $CommandName (exit $nativeExitCode). Context: $Context"
    }
    $stdoutLines
}

function Test-CheckedCommand {
    param([Parameter(Mandatory = $true)][string[]]$CommandCandidates)
    foreach ($candidate in $CommandCandidates) {
        if (Get-Command $candidate -ErrorAction SilentlyContinue) {
            return $candidate
        }
    }
    return $null
}

function Get-RepositoryRoot {
    (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
}

function Get-SafeIdentifier {
    param([Parameter(Mandatory = $true)][string]$Value)
    if ($Value.Length -le 12) { return $Value }
    return "{0}…{1}" -f $Value.Substring(0, 8), $Value.Substring($Value.Length - 4)
}

function Assert-ValidEmail {
    param([Parameter(Mandatory = $true)][string]$Email)
    if ($Email -notmatch '^[^\s@]+@[^\s@]+\.[^\s@]+$') {
        throw 'BudgetAlertEmail must be a valid private operator email supplied outside Git.'
    }
}

function Assert-UrlSafeSecretPlaceholder {
    param([Parameter(Mandatory = $true)][string]$Value)
    if ($Value -notmatch '^[A-Za-z0-9_-]{16,}$') {
        throw 'Secret input must be URL-safe and must not contain whitespace.'
    }
}
