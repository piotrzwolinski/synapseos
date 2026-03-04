# =============================================================================
# Step 3: Push Images to Azure Container Registry (INTERACTIVE)
# =============================================================================
# Run this on Windows App (PowerShell) after transferring files from Mac.
#
# Usage:
#   .\3-push-images.ps1 -Mode Docker -FilesDir C:\deploy
#   .\3-push-images.ps1 -Mode AcrBuild -FilesDir C:\deploy
#
# Press Ctrl+C at any time to abort.
# =============================================================================

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("Docker", "AcrBuild")]
    [string]$Mode,

    [Parameter(Mandatory=$true)]
    [string]$FilesDir
)

$ErrorActionPreference = "Stop"

# --- Configuration (must match step 1) ---
$RESOURCE_GROUP = "synapse-rg"
$ACR_NAME       = "synapseosacr"
$ACR_SERVER     = "${ACR_NAME}.azurecr.io"
$TAG            = "v1"

$BACKEND_IMAGE  = "${ACR_SERVER}/synapse-backend"
$FRONTEND_IMAGE = "${ACR_SERVER}/synapse-frontend"

function Confirm-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host $Message -ForegroundColor Yellow
    $response = Read-Host "Continue? [y/N]"
    if ($response -ne "y" -and $response -ne "Y") {
        Write-Host "Aborted." -ForegroundColor Red
        exit 0
    }
}

# --- Preflight ---
Write-Host "`n=== PREFLIGHT ===" -ForegroundColor Cyan
try {
    $account = az account show --output json | ConvertFrom-Json
    Write-Host "Azure:        $($account.user.name) @ $($account.name)" -ForegroundColor Green
} catch {
    Write-Host "ERROR: Run 'az login' first" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $FilesDir)) {
    Write-Host "ERROR: Directory not found: $FilesDir" -ForegroundColor Red
    exit 1
}

# Verify ACR exists
try {
    az acr show --name $ACR_NAME --output none
    Write-Host "ACR:          $ACR_SERVER (exists)" -ForegroundColor Green
} catch {
    Write-Host "ERROR: ACR '$ACR_NAME' not found. Run step 1 first." -ForegroundColor Red
    exit 1
}

Write-Host "Mode:         $Mode" -ForegroundColor White
Write-Host "Files dir:    $FilesDir" -ForegroundColor White

# List files in directory
Write-Host "`nFiles found:" -ForegroundColor Gray
Get-ChildItem $FilesDir -Filter "*.tar.gz" | ForEach-Object {
    Write-Host "  $($_.Name) ($([math]::Round($_.Length / 1MB, 1)) MB)" -ForegroundColor White
}

# =============================================================================
# PATH A: Docker — load pre-built images and push
# =============================================================================
if ($Mode -eq "Docker") {
    Write-Host "`n=== PATH A: Docker load + push ===" -ForegroundColor Cyan
    Write-Host "Source code is NOT in these images (Cython-compiled .so only)" -ForegroundColor Gray

    # Check Docker
    try {
        docker info | Out-Null
        Write-Host "Docker:       running" -ForegroundColor Green
    } catch {
        Write-Host "ERROR: Docker is not running." -ForegroundColor Red
        Write-Host "Either start Docker Desktop, or use: -Mode AcrBuild" -ForegroundColor Yellow
        exit 1
    }

    # Login to ACR
    Confirm-Step "Login to ACR '$ACR_NAME'? (az acr login)"
    az acr login --name $ACR_NAME

    # --- Backend ---
    $backendTar = Join-Path $FilesDir "backend-image.tar.gz"
    if (-not (Test-Path $backendTar)) {
        Write-Host "ERROR: Not found: $backendTar" -ForegroundColor Red
        exit 1
    }

    Write-Host "`n--- Backend Image ---" -ForegroundColor Cyan
    Write-Host "  File:   $backendTar" -ForegroundColor White
    Write-Host "  Target: ${BACKEND_IMAGE}:${TAG}" -ForegroundColor White
    Write-Host "  Action: docker load -> docker tag -> docker push" -ForegroundColor Gray

    Confirm-Step "Load and push BACKEND image to ACR?"

    Write-Host "Loading..." -ForegroundColor Gray
    docker load -i $backendTar
    docker tag synapse-backend:latest "${BACKEND_IMAGE}:${TAG}"
    Write-Host "Pushing to ACR..." -ForegroundColor Gray
    docker push "${BACKEND_IMAGE}:${TAG}"
    Write-Host "Backend pushed!" -ForegroundColor Green

    # --- Frontend ---
    $frontendTar = Join-Path $FilesDir "frontend-image.tar.gz"
    if (-not (Test-Path $frontendTar)) {
        Write-Host "ERROR: Not found: $frontendTar" -ForegroundColor Red
        exit 1
    }

    Write-Host "`n--- Frontend Image ---" -ForegroundColor Cyan
    Write-Host "  File:   $frontendTar" -ForegroundColor White
    Write-Host "  Target: ${FRONTEND_IMAGE}:${TAG}" -ForegroundColor White

    Confirm-Step "Load and push FRONTEND image to ACR?"

    Write-Host "Loading..." -ForegroundColor Gray
    docker load -i $frontendTar
    docker tag synapse-frontend:latest "${FRONTEND_IMAGE}:${TAG}"
    Write-Host "Pushing to ACR..." -ForegroundColor Gray
    docker push "${FRONTEND_IMAGE}:${TAG}"
    Write-Host "Frontend pushed!" -ForegroundColor Green
}

# =============================================================================
# PATH B: AcrBuild — build from source context in Azure
# =============================================================================
if ($Mode -eq "AcrBuild") {
    Write-Host "`n=== PATH B: az acr build (remote build) ===" -ForegroundColor Cyan
    Write-Host "Source code is sent to a temporary Azure build agent." -ForegroundColor Gray
    Write-Host "The build agent is deleted after the build. Final image has .so only." -ForegroundColor Gray

    # --- Backend ---
    $backendCtx = Join-Path $FilesDir "backend-context.tar.gz"
    if (-not (Test-Path $backendCtx)) {
        Write-Host "ERROR: Not found: $backendCtx" -ForegroundColor Red
        exit 1
    }

    Write-Host "`n--- Backend Build ---" -ForegroundColor Cyan
    Write-Host "  Context:    $backendCtx" -ForegroundColor White
    Write-Host "  Dockerfile: Dockerfile.dist (Cython compilation)" -ForegroundColor White
    Write-Host "  Target:     ${ACR_SERVER}/synapse-backend:${TAG}" -ForegroundColor White
    Write-Host "  Duration:   ~5 minutes (Cython compilation)" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  What happens:" -ForegroundColor Gray
    Write-Host "    1. Tar is uploaded to Azure build agent" -ForegroundColor Gray
    Write-Host "    2. Dockerfile.dist runs: compile .py -> .so" -ForegroundColor Gray
    Write-Host "    3. Final image stored in ACR (only .so, no .py)" -ForegroundColor Gray
    Write-Host "    4. Build agent + source context auto-deleted" -ForegroundColor Gray

    Confirm-Step "Build BACKEND image in ACR?"

    az acr build `
        --registry $ACR_NAME `
        --resource-group $RESOURCE_GROUP `
        --image "synapse-backend:${TAG}" `
        --file Dockerfile.dist `
        --timeout 1200 `
        $backendCtx

    Write-Host "Backend built and stored in ACR!" -ForegroundColor Green

    # --- Frontend ---
    $frontendCtx = Join-Path $FilesDir "frontend-context.tar.gz"
    if (-not (Test-Path $frontendCtx)) {
        Write-Host "ERROR: Not found: $frontendCtx" -ForegroundColor Red
        exit 1
    }

    Write-Host "`n--- Frontend Build ---" -ForegroundColor Cyan
    Write-Host "  Context:    $frontendCtx" -ForegroundColor White
    Write-Host "  Dockerfile: Dockerfile" -ForegroundColor White
    Write-Host "  Target:     ${ACR_SERVER}/synapse-frontend:${TAG}" -ForegroundColor White
    Write-Host "  Note:       API URL is placeholder — rebuild after backend URL is known" -ForegroundColor Yellow

    Confirm-Step "Build FRONTEND image in ACR?"

    az acr build `
        --registry $ACR_NAME `
        --resource-group $RESOURCE_GROUP `
        --image "synapse-frontend:${TAG}" `
        --file Dockerfile `
        --build-arg "NEXT_PUBLIC_API_URL=https://PLACEHOLDER" `
        --timeout 600 `
        $frontendCtx

    Write-Host "Frontend built and stored in ACR!" -ForegroundColor Green
}

# --- Verify ---
Write-Host "`n=== VERIFY: Images in ACR ===" -ForegroundColor Cyan
az acr repository list --name $ACR_NAME --output table

Write-Host "`nBackend tags:" -ForegroundColor Gray
az acr repository show-tags --name $ACR_NAME --repository synapse-backend --output table 2>$null

Write-Host "Frontend tags:" -ForegroundColor Gray
az acr repository show-tags --name $ACR_NAME --repository synapse-frontend --output table 2>$null

Write-Host "`n=== IMAGES IN ACR ===" -ForegroundColor Green
Write-Host "Next step: .\4-deploy-apps.ps1" -ForegroundColor Cyan
