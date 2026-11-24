[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ResourceGroup,

    [string]$Location = "eastasia",

    [string]$NamePrefix = "tryon",

    [string]$ImageTag = "v1",

    [Parameter(Mandatory = $true)]
    [string]$ParametersFile,

    [switch]$SkipImageBuild,
    [switch]$SkipAssetUpload,
    [switch]$UseLocalDocker
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$BicepFile = Join-Path $RepoRoot "deploy\azure\aca\main.bicep"

if (-not (Test-Path $BicepFile)) {
    throw "Bicep template not found: $BicepFile"
}
if (-not (Test-Path $ParametersFile)) {
    throw "Parameters file not found: $ParametersFile"
}

Write-Host "[1/7] Ensuring resource group '$ResourceGroup' in '$Location'..."
az group create --name $ResourceGroup --location $Location --only-show-errors | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Failed to ensure resource group '$ResourceGroup'." }

Write-Host "[2/7] Phase 1: Provisioning core Azure infrastructure, RBAC, and ACA environment..."
$phase1Json = az deployment group create `
    --resource-group $ResourceGroup `
    --template-file $BicepFile `
    --parameters "@$ParametersFile" `
    --parameters namePrefix=$NamePrefix imageTag=$ImageTag deployWorkloads=false `
    --only-show-errors `
    --output json
if ($LASTEXITCODE -ne 0) { throw "Phase 1 Bicep deployment failed." }
$phase1Out = ($phase1Json | ConvertFrom-Json).properties.outputs

$acrServer = $phase1Out.acrLoginServer.value
$acrName = ($acrServer -split '\.')[0]
$storageAccount = $phase1Out.storageAccountName.value
$dbInitJob = $phase1Out.dbInitJobName.value
$mainUrl = $phase1Out.mainAppUrl.value
$workbenchUrl = $phase1Out.workbenchAppUrl.value
$adminUrl = $phase1Out.adminAppUrl.value
$workbenchTryonUrl = "$($workbenchUrl.TrimEnd('/'))/static/index.html"

Write-Host "  ACR: $acrServer | Storage: $storageAccount"
Write-Host "  URLs: Main=$mainUrl | Workbench=$workbenchUrl | Admin=$adminUrl"

if (-not $SkipImageBuild) {
    Write-Host "[3/7] Building and pushing container images to ACR ($acrName)..."
    $appRoot = Join-Path $RepoRoot "main-app"
    $wbRoot = Join-Path $RepoRoot "PJ111ForGemini\Cloud"

    $imageSpecs = @(
        @{
            Name       = "${NamePrefix}-main:${ImageTag}"
            Dockerfile = (Join-Path $appRoot "Dockerfile")
            Context    = $appRoot
            BuildArgs  = @(
                "VITE_API_BASE_URL=/",
                "VITE_TRYON_BASE_URL=$workbenchTryonUrl",
                "VITE_ADMIN_BASE_URL=$adminUrl"
            )
        },
        @{
            Name       = "${NamePrefix}-admin:${ImageTag}"
            Dockerfile = (Join-Path $appRoot "admin\Dockerfile")
            Context    = $appRoot
            BuildArgs  = @(
                "VITE_ADMIN_API_BASE_URL=/",
                "VITE_ADMIN_API_URL=/"
            )
        },
        @{
            Name       = "${NamePrefix}-workbench:${ImageTag}"
            Dockerfile = (Join-Path $wbRoot "Dockerfile")
            Context    = $wbRoot
            BuildArgs  = @()
        },
        @{
            Name       = "${NamePrefix}-worker:${ImageTag}"
            Dockerfile = (Join-Path $wbRoot "Dockerfile.worker")
            Context    = $wbRoot
            BuildArgs  = @()
        }
    )

    $useLocal = [bool]$UseLocalDocker
    $dockerMode = ""
    $acrLoggedIn = $false

    $convertToWslPath = {
        param([string]$WinPath)
        $norm = $WinPath -replace '\\', '/'
        $out = (& wsl -d Ubuntu -- wslpath -a "$norm" 2>$null | Out-String).Trim()
        if ($LASTEXITCODE -ne 0 -or -not $out) {
            throw "Failed to convert Windows path to WSL path: $WinPath"
        }
        return $out
    }

    foreach ($spec in $imageSpecs) {
        $fullImage = "$acrServer/$($spec.Name)"
        if (-not $useLocal) {
            $acrArgs = @("acr", "build", "--registry", $acrName, "--image", $spec.Name, "--file", $spec.Dockerfile)
            foreach ($ba in $spec.BuildArgs) {
                $acrArgs += @("--build-arg", $ba)
            }
            $acrArgs += @($spec.Context, "--only-show-errors")

            $prevEap = $ErrorActionPreference
            $ErrorActionPreference = "Continue"
            try {
                $acrOut = & az @acrArgs 2>&1
                $acrExit = $LASTEXITCODE
            }
            finally {
                $ErrorActionPreference = $prevEap
            }
            if ($acrExit -eq 0) {
                continue
            }
            $acrText = ($acrOut | ForEach-Object { $_.ToString() }) -join "`n"
            if ($acrText -match "TasksOperationsNotAllowed") {
                Write-Warning "ACR Tasks is blocked on this subscription (TasksOperationsNotAllowed); switching to local Docker build + push."
                $useLocal = $true
            }
            else {
                throw "Failed to build $($spec.Name): $acrText"
            }
        }

        if (-not $dockerMode) {
            $prevEap = $ErrorActionPreference
            $ErrorActionPreference = "Continue"
            try {
                if (Get-Command docker -ErrorAction SilentlyContinue) {
                    & docker info *> $null
                    if ($LASTEXITCODE -eq 0) { $dockerMode = "windows" }
                }
                if (-not $dockerMode -and (Get-Command wsl -ErrorAction SilentlyContinue)) {
                    & wsl -d Ubuntu -u root -- docker info *> $null
                    if ($LASTEXITCODE -eq 0) { $dockerMode = "wsl" }
                }
            }
            finally {
                $ErrorActionPreference = $prevEap
            }
            if (-not $dockerMode) {
                throw "Neither Windows Docker daemon nor WSL Ubuntu Docker daemon is available."
            }
            Write-Host "  Using local Docker mode: $dockerMode"
        }

        if (-not $acrLoggedIn) {
            if ($dockerMode -eq "windows") {
                az acr login --name $acrName --only-show-errors | Out-Null
                if ($LASTEXITCODE -ne 0) { throw "Failed to authenticate Windows Docker to ACR '$acrName'." }
            }
            else {
                $acrTokJson = az acr login --name $acrName --expose-token --output json --only-show-errors
                if ($LASTEXITCODE -ne 0) { throw "Failed to get ACR token for '$acrName'." }
                $acrTok = ($acrTokJson | ConvertFrom-Json).accessToken
                if (-not $acrTok) { throw "Empty ACR accessToken returned for '$acrName'." }
                $prevEap = $ErrorActionPreference
                $ErrorActionPreference = "Continue"
                try {
                    $acrTok | & wsl -d Ubuntu -u root -- docker login $acrServer -u "00000000-0000-0000-0000-000000000000" --password-stdin | Out-Null
                    $loginExit = $LASTEXITCODE
                }
                finally {
                    $ErrorActionPreference = $prevEap
                }
                if ($loginExit -ne 0) { throw "Failed to authenticate WSL Docker to ACR '$acrServer'." }
            }
            $acrLoggedIn = $true
        }

        Write-Host "  Building $fullImage ($dockerMode, linux/amd64)..."
        if ($dockerMode -eq "windows") {
            $dockerArgs = @("build", "--platform", "linux/amd64", "-t", $fullImage, "-f", $spec.Dockerfile)
            foreach ($ba in $spec.BuildArgs) {
                $dockerArgs += @("--build-arg", $ba)
            }
            $dockerArgs += $spec.Context
            $prevEap = $ErrorActionPreference
            $ErrorActionPreference = "Continue"
            try {
                & docker @dockerArgs
                $buildExit = $LASTEXITCODE
            }
            finally {
                $ErrorActionPreference = $prevEap
            }
            if ($buildExit -ne 0) { throw "Local docker build failed for $fullImage." }

            Write-Host "  Pushing $fullImage..."
            $pushExit = 1
            for ($attempt = 1; $attempt -le 3; $attempt++) {
                $prevEap = $ErrorActionPreference
                $ErrorActionPreference = "Continue"
                try {
                    & docker push $fullImage
                    $pushExit = $LASTEXITCODE
                }
                finally {
                    $ErrorActionPreference = $prevEap
                }
                if ($pushExit -eq 0) { break }
                if ($attempt -lt 3) { Start-Sleep -Seconds 5 }
            }
            if ($pushExit -ne 0) { throw "docker push failed for $fullImage." }
        }
        else {
            $wslDockerfile = & $convertToWslPath $spec.Dockerfile
            $wslContext = & $convertToWslPath $spec.Context
            $wslBuildArgs = @("-d", "Ubuntu", "-u", "root", "--", "docker", "buildx", "build", "--platform", "linux/amd64", "--load", "--progress=plain", "-t", $fullImage, "-f", $wslDockerfile)
            foreach ($ba in $spec.BuildArgs) {
                $wslBuildArgs += @("--build-arg", $ba)
            }
            $wslBuildArgs += $wslContext
            $prevEap = $ErrorActionPreference
            $ErrorActionPreference = "Continue"
            try {
                & wsl @wslBuildArgs
                $buildExit = $LASTEXITCODE
            }
            finally {
                $ErrorActionPreference = $prevEap
            }
            if ($buildExit -ne 0) { throw "WSL docker build failed for $fullImage." }

            Write-Host "  Pushing $fullImage..."
            $pushExit = 1
            for ($attempt = 1; $attempt -le 3; $attempt++) {
                $prevEap = $ErrorActionPreference
                $ErrorActionPreference = "Continue"
                try {
                    & wsl -d Ubuntu -u root -- docker push $fullImage
                    $pushExit = $LASTEXITCODE
                }
                finally {
                    $ErrorActionPreference = $prevEap
                }
                if ($pushExit -eq 0) { break }
                if ($attempt -lt 3) { Start-Sleep -Seconds 5 }
            }
            if ($pushExit -ne 0) { throw "WSL docker push failed for $fullImage." }
        }
    }
}

if (-not $SkipAssetUpload) {
    Write-Host "[4/7] Staging & uploading all verified product and sample model assets to Storage '$storageAccount'..."
    $probeOk = $false
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        az storage blob list --account-name $storageAccount --container-name "product-images" --auth-mode login --num-results 1 --only-show-errors *> $null
        if ($LASTEXITCODE -eq 0) { $probeOk = $true }
        if (-not $probeOk) {
            $principalId = (az ad signed-in-user show --query id --output tsv --only-show-errors 2>$null | Out-String).Trim()
            $storageId = (az storage account show --resource-group $ResourceGroup --name $storageAccount --query id --output tsv --only-show-errors | Out-String).Trim()
            if ($principalId -and $storageId) {
                Write-Host "  Assigning Storage Blob Data Contributor to current operator for initial asset upload..."
                az role assignment create --assignee $principalId --role "Storage Blob Data Contributor" --scope $storageId --only-show-errors *> $null
                for ($r = 0; $r -lt 8; $r++) {
                    Start-Sleep -Seconds 10
                    az storage blob list --account-name $storageAccount --container-name "product-images" --auth-mode login --num-results 1 --only-show-errors *> $null
                    if ($LASTEXITCODE -eq 0) { $probeOk = $true; break }
                }
            }
        }
    }
    finally {
        $ErrorActionPreference = $prevEap
    }
    if (-not $probeOk) {
        throw "Current operator lacks Storage Blob Data Contributor permission on '$storageAccount' (RBAC may still be propagating; wait 1 minute and retry)."
    }

    $stageRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("aca-assets-" + [Guid]::NewGuid().ToString("N"))
    $productStage = Join-Path $stageRoot "product-images"
    $manifestPath = Join-Path $stageRoot "catalog-manifest.json"
    try {
        $catalogScript = Join-Path $RepoRoot "scripts\release\catalog_assets.py"
        python $catalogScript --root $RepoRoot --manifest $manifestPath --stage-dir $productStage
        if ($LASTEXITCODE -ne 0) { throw "catalog_assets.py staging failed." }

        az storage blob upload-batch `
            --account-name $storageAccount `
            --auth-mode login `
            --destination "product-images" `
            --source $productStage `
            --content-cache-control "public, max-age=31536000, immutable" `
            --overwrite `
            --only-show-errors | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Product blob upload-batch failed." }
    } finally {
        if (Test-Path $stageRoot) {
            Remove-Item -LiteralPath $stageRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    $sampleScript = Join-Path $RepoRoot "deploy\azure\scripts\upload-sample-models.ps1"
    if (Test-Path $sampleScript) {
        & $sampleScript -StorageAccountName $storageAccount -ContainerName "product-images"
    }
}

Write-Host "[5/7] Phase 2: Deploying ACA apps and event-driven queue worker job..."
$deployJson = az deployment group create `
    --resource-group $ResourceGroup `
    --template-file $BicepFile `
    --parameters "@$ParametersFile" `
    --parameters namePrefix=$NamePrefix imageTag=$ImageTag deployWorkloads=true `
    --only-show-errors `
    --output json
if ($LASTEXITCODE -ne 0) { throw "Phase 2 Bicep deployment failed." }
$deployOut = ($deployJson | ConvertFrom-Json).properties.outputs
$mainUrl = $deployOut.mainAppUrl.value
$workbenchUrl = $deployOut.workbenchAppUrl.value
$adminUrl = $deployOut.adminAppUrl.value

Write-Host "[6/7] Running one-off DB initialization job '$dbInitJob'..."
$execJson = az containerapp job start --name $dbInitJob --resource-group $ResourceGroup --output json
if ($LASTEXITCODE -ne 0) { throw "Failed to start DB init job '$dbInitJob'." }
$execName = ($execJson | ConvertFrom-Json).name
$finalStatus = ""
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Seconds 10
    $status = az containerapp job execution show `
        --name $dbInitJob `
        --resource-group $ResourceGroup `
        --job-execution-name $execName `
        --query "properties.status" `
        --output tsv
    Write-Host "  DB init job status: $status"
    $finalStatus = $status
    if ($status -eq "Succeeded") { break }
    if ($status -eq "Failed") { throw "DB init job '$execName' failed." }
}
if ($finalStatus -ne "Succeeded") {
    throw "DB init job '$execName' did not succeed in time (status=$finalStatus)."
}

Write-Host "[7/7] Running scale-to-zero smoke tests..."
& (Join-Path $PSScriptRoot "smoke-test-aca.ps1") `
    -MainUrl $mainUrl `
    -WorkbenchUrl $workbenchUrl `
    -AdminUrl $adminUrl
