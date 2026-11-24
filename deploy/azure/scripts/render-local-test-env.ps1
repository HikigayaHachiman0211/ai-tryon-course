[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)][string]$OutputPath,
    [Parameter(Mandatory = $false)][switch]$Force
)

. (Join-Path $PSScriptRoot 'common.ps1')

$repositoryRoot = Get-RepositoryRoot
if (-not $OutputPath) { $OutputPath = Join-Path $repositoryRoot 'deploy\azure\.env.azure.test' }
$resolvedOutputPath = [System.IO.Path]::GetFullPath($OutputPath)
if ((Test-Path -LiteralPath $resolvedOutputPath) -and -not $Force) {
    throw "Refusing to overwrite existing local test environment without -Force: $resolvedOutputPath"
}
$outputDirectory = Split-Path -Parent $resolvedOutputPath
New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null

$localTestValues = @(
    '# GENERATED LOCAL-ONLY TEST VALUES. Not production credentials. Ignored by Git.',
    'APP_ENV=development',
    'COMPOSE_PROJECT_NAME=ai-tryon-course-test',
    "APPLICATION_ENV_FILE=$resolvedOutputPath",
    'IMAGE_NAMESPACE=local/ai-tryon-course',
    'RELEASE_ID=local-test',
    'AZURE_FQDN=localhost',
    'MAIN_PUBLIC_URL=https://localhost',
    'ADMIN_PUBLIC_URL=https://localhost:8443',
    'WORKBENCH_PUBLIC_URL=https://localhost:9443',
    'WORKBENCH_ENTRY_URL=https://localhost:9443/static/index.html',
    'CORS_ALLOW_ORIGINS=https://localhost,https://localhost:8443,https://localhost:9443',
    'ACME_EMAIL=course@example.invalid',
    'POSTGRES_DB=ai_tryon_test',
    'POSTGRES_USER=ai_tryon_test',
    'POSTGRES_PASSWORD=test_password_only_0123456789',
    'DATABASE_URL=postgresql+psycopg://ai_tryon_test:test_password_only_0123456789@postgres:5432/ai_tryon_test',
    'AI_CONFIG_DATABASE_URL=postgresql+psycopg://ai_tryon_test:test_password_only_0123456789@postgres:5432/ai_tryon_test',
    'OBJECT_STORAGE_PROVIDER=local',
    'AZURE_STORAGE_ACCOUNT_NAME=',
    'AZURE_STORAGE_CONNECTION_STRING=',
    'AZURE_PRODUCT_CONTAINER=product-assets',
    'AZURE_MEDIA_CONTAINER=course-media',
    'AZURE_BACKUP_CONTAINER=backups',
    'PUBLIC_IMAGE_BASE_URL=https://local.invalid/product-assets',
    'PUBLIC_MEDIA_BASE_URL=https://local.invalid/course-media',
    'OBJECT_STORAGE_LOCAL_ROOT=/tmp/ai-tryon-course-test-storage',
    'JWT_SECRET_KEY=test-only-jwt-secret-012345678901234567890',
    'FERNET_SECRET_KEY=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=',
    'INGEST_SECRET_KEY=test-only-ingest-secret-0123456789',
    'ADMIN_INIT_USERNAME=test-admin',
    'ADMIN_INIT_PASSWORD=test-only-admin-password-012345',
    'GEMINI_API_KEY=',
    'MIMO_API_KEY=',
    'DEEPSEEK_API_KEY=',
    'TRYON_FLASH_MODEL=gemini-2.5-flash-image',
    'MIMO_MODEL=',
    'ASR_MODEL=mimo-v2.5-asr',
    'TTS_MODEL=mimo-v2.5-tts',
    'HISTORY_DIR=/tmp/ai-tryon-course-test-history',
    'VOICE_CLONE_UPLOAD_DIR=/tmp/ai-tryon-course-test-voice-clones',
    'UPLOAD_DIR=/tmp/ai-tryon-course-test-uploads',
    'ASSET_DIR=/tmp/ai-tryon-course-test-assets',
    'WORKBENCH_HISTORY_DIR=/tmp/ai-tryon-course-test-workbench-history',
    'VITE_RECOMMEND_APP_URL=https://localhost',
    'VITE_TRYON_EMBED_MODE=standalone'
)
$localTestValues | Set-Content -LiteralPath $resolvedOutputPath -Encoding utf8
Write-Output "generated local-only test env: $resolvedOutputPath"
Write-Output 'sensitivity: test-only values; no production credentials; ignored by Git'
