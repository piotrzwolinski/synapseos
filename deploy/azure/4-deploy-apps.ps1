# =============================================================================
# Step 4: Deploy Container Apps (INTERACTIVE — confirms each app)
# =============================================================================
# Run this on Windows App (PowerShell) after images are in ACR (step 3).
#
# Deploys in order:
#   1. FalkorDB   (internal, Azure Files mount)
#   2. Backend    (external, connects to FalkorDB)
#   3. Frontend   (external, API URL pointing to backend)
#
# Usage:
#   .\4-deploy-apps.ps1
#   .\4-deploy-apps.ps1 -RebuildFrontend   # Rebuild frontend with correct API URL
#
# Press Ctrl+C at any time to abort.
# Cleanup:  az group delete -n synapse-rg --yes
# =============================================================================

param(
    [switch]$RebuildFrontend
)

$ErrorActionPreference = "Stop"

# --- Configuration (must match steps 1 and 3) ---
$RESOURCE_GROUP    = "synapse-rg"
$ACA_ENV           = "synapse-env"
$ACR_NAME          = "synapseosacr"
$ACR_SERVER        = "${ACR_NAME}.azurecr.io"
$TAG               = "v1"

# App names
$FALKORDB_APP      = "synapse-falkordb"
$BACKEND_APP       = "synapse-backend"
$FRONTEND_APP      = "synapse-frontend"

# --- SECRETS (CHANGE THESE!) ---
$GEMINI_API_KEY    = "YOUR_GEMINI_API_KEY"
$FALKORDB_PASSWORD = "YOUR_FALKORDB_PASSWORD"
$JWT_SECRET_KEY    = "YOUR_JWT_SECRET"

# --- Backend config ---
$DOMAIN_ID         = "mann_hummel"
$FALKORDB_GRAPH    = "synapse"

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
$account = az account show --output json | ConvertFrom-Json
Write-Host "Azure:  $($account.user.name) @ $($account.name)" -ForegroundColor Green

# Verify secrets are set
if ($GEMINI_API_KEY -eq "YOUR_GEMINI_API_KEY") {
    Write-Host ""
    Write-Host "WARNING: You haven't set the secrets!" -ForegroundColor Red
    Write-Host "Edit this script and replace:" -ForegroundColor Yellow
    Write-Host '  $GEMINI_API_KEY    = "YOUR_GEMINI_API_KEY"' -ForegroundColor Gray
    Write-Host '  $FALKORDB_PASSWORD = "YOUR_FALKORDB_PASSWORD"' -ForegroundColor Gray
    Write-Host '  $JWT_SECRET_KEY    = "YOUR_JWT_SECRET"' -ForegroundColor Gray
    Write-Host ""
    Write-Host "Or set them interactively now:" -ForegroundColor Yellow
    $GEMINI_API_KEY = Read-Host "GEMINI_API_KEY"
    $FALKORDB_PASSWORD = Read-Host "FALKORDB_PASSWORD"
    $JWT_SECRET_KEY = Read-Host "JWT_SECRET_KEY"

    if (-not $GEMINI_API_KEY -or -not $FALKORDB_PASSWORD -or -not $JWT_SECRET_KEY) {
        Write-Host "ERROR: All secrets are required." -ForegroundColor Red
        exit 1
    }
}

# Get ACR credentials
$ACR_USERNAME = (az acr credential show --name $ACR_NAME --query "username" --output tsv)
$ACR_PASSWORD = (az acr credential show --name $ACR_NAME --query "passwords[0].value" --output tsv)

# =============================================================================
# PLAN: Show what will be deployed
# =============================================================================
Write-Host "`n=== DEPLOYMENT PLAN ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "  1. FalkorDB (graph database)" -ForegroundColor White
Write-Host "     Image:   falkordb/falkordb:latest (public)" -ForegroundColor Gray
Write-Host "     Ingress: INTERNAL only (not accessible from internet)" -ForegroundColor Gray
Write-Host "     Storage: Azure Files mount at /data" -ForegroundColor Gray
Write-Host "     CPU/RAM: 1.0 vCPU / 2 GB" -ForegroundColor Gray
Write-Host ""
Write-Host "  2. Backend (FastAPI)" -ForegroundColor White
Write-Host "     Image:   ${ACR_SERVER}/synapse-backend:${TAG}" -ForegroundColor Gray
Write-Host "     Ingress: EXTERNAL (HTTPS, public URL)" -ForegroundColor Gray
Write-Host "     CPU/RAM: 1.0 vCPU / 2 GB, auto-scale 1-3" -ForegroundColor Gray
Write-Host ""
Write-Host "  3. Frontend (Next.js)" -ForegroundColor White
Write-Host "     Image:   ${ACR_SERVER}/synapse-frontend:${TAG}" -ForegroundColor Gray
Write-Host "     Ingress: EXTERNAL (HTTPS, public URL)" -ForegroundColor Gray
Write-Host "     CPU/RAM: 0.5 vCPU / 1 GB, auto-scale 1-2" -ForegroundColor Gray
Write-Host ""
Write-Host "  Estimated running cost: ~$50-100/month" -ForegroundColor Gray
Write-Host "  Cleanup: az group delete -n $RESOURCE_GROUP --yes" -ForegroundColor Gray

Confirm-Step "Deploy all 3 container apps?"

# =============================================================================
# 1. FALKORDB
# =============================================================================
Write-Host "`n=== 1/3 FALKORDB ===" -ForegroundColor Cyan
Write-Host "Deploying FalkorDB graph database (internal only)..." -ForegroundColor Gray
Write-Host "  Password protected: --requirepass ********" -ForegroundColor Gray
Write-Host "  Data persistence:   Azure Files at /data" -ForegroundColor Gray
Write-Host "  Auto-save:          every 60 seconds" -ForegroundColor Gray

Confirm-Step "Deploy FalkorDB container?"

az containerapp create `
    --name $FALKORDB_APP `
    --resource-group $RESOURCE_GROUP `
    --environment $ACA_ENV `
    --image "falkordb/falkordb:latest" `
    --target-port 6379 `
    --ingress "internal" `
    --transport "tcp" `
    --min-replicas 1 `
    --max-replicas 1 `
    --cpu 1.0 `
    --memory 2.0Gi `
    --env-vars "REDIS_ARGS=--requirepass $FALKORDB_PASSWORD --save 60 1" `
    --output table

Write-Host "FalkorDB container created." -ForegroundColor Green

# Add volume mount via YAML update
Write-Host "Attaching Azure Files volume for /data persistence..." -ForegroundColor Gray
$falkordbYaml = @"
properties:
  template:
    volumes:
      - name: falkordb-volume
        storageName: falkordbstorage
        storageType: AzureFile
    containers:
      - name: falkordb
        image: falkordb/falkordb:latest
        resources:
          cpu: 1.0
          memory: 2.0Gi
        env:
          - name: REDIS_ARGS
            value: "--requirepass $FALKORDB_PASSWORD --save 60 1 --dir /data"
        volumeMounts:
          - volumeName: falkordb-volume
            mountPath: /data
"@
$yamlPath = [System.IO.Path]::GetTempPath() + "falkordb-update.yaml"
$falkordbYaml | Out-File -FilePath $yamlPath -Encoding utf8

az containerapp update `
    --name $FALKORDB_APP `
    --resource-group $RESOURCE_GROUP `
    --yaml $yamlPath `
    --output table

Remove-Item $yamlPath -ErrorAction SilentlyContinue

# Get internal FQDN
$FALKORDB_FQDN = (az containerapp show `
    --name $FALKORDB_APP `
    --resource-group $RESOURCE_GROUP `
    --query "properties.configuration.ingress.fqdn" `
    --output tsv)

Write-Host "FalkorDB internal FQDN: $FALKORDB_FQDN" -ForegroundColor Green
Write-Host "Waiting 30s for FalkorDB to initialize..." -ForegroundColor Gray
Start-Sleep -Seconds 30

# =============================================================================
# 2. BACKEND
# =============================================================================
Write-Host "`n=== 2/3 BACKEND ===" -ForegroundColor Cyan
Write-Host "Deploying FastAPI backend..." -ForegroundColor Gray
Write-Host "  Image:         ${ACR_SERVER}/synapse-backend:${TAG}" -ForegroundColor Gray
Write-Host "  FalkorDB host: $FALKORDB_FQDN" -ForegroundColor Gray
Write-Host "  Domain:        $DOMAIN_ID" -ForegroundColor Gray
Write-Host "  Secrets:       GEMINI_API_KEY, FALKORDB_PASSWORD, JWT_SECRET_KEY" -ForegroundColor Gray
Write-Host "  Health check:  GET /health" -ForegroundColor Gray

Confirm-Step "Deploy Backend container?"

az containerapp create `
    --name $BACKEND_APP `
    --resource-group $RESOURCE_GROUP `
    --environment $ACA_ENV `
    --image "${ACR_SERVER}/synapse-backend:${TAG}" `
    --registry-server $ACR_SERVER `
    --registry-username $ACR_USERNAME `
    --registry-password $ACR_PASSWORD `
    --target-port 8000 `
    --ingress "external" `
    --min-replicas 1 `
    --max-replicas 3 `
    --cpu 1.0 `
    --memory 2.0Gi `
    --env-vars `
        "GEMINI_API_KEY=$GEMINI_API_KEY" `
        "FALKORDB_HOST=$FALKORDB_FQDN" `
        "FALKORDB_PORT=6379" `
        "FALKORDB_PASSWORD=$FALKORDB_PASSWORD" `
        "FALKORDB_GRAPH=$FALKORDB_GRAPH" `
        "DOMAIN_ID=$DOMAIN_ID" `
        "JWT_SECRET_KEY=$JWT_SECRET_KEY" `
        "PYTHONUNBUFFERED=1" `
        "AUTH_DISABLED=false" `
    --output table

# Get Backend URL
$BACKEND_FQDN = (az containerapp show `
    --name $BACKEND_APP `
    --resource-group $RESOURCE_GROUP `
    --query "properties.configuration.ingress.fqdn" `
    --output tsv)
$BACKEND_URL = "https://$BACKEND_FQDN"

Write-Host "Backend URL: $BACKEND_URL" -ForegroundColor Green

# Health check
Write-Host "Waiting 20s for backend to start..." -ForegroundColor Gray
Start-Sleep -Seconds 20
Write-Host "Testing health endpoint..." -ForegroundColor Gray
try {
    $health = Invoke-RestMethod -Uri "$BACKEND_URL/health" -TimeoutSec 30
    Write-Host "Health: $($health.status)" -ForegroundColor Green
} catch {
    Write-Host "Health check didn't respond yet (may still be starting)." -ForegroundColor Yellow
    Write-Host "Check logs: az containerapp logs show -n $BACKEND_APP -g $RESOURCE_GROUP --follow" -ForegroundColor Gray
}

# =============================================================================
# 3. FRONTEND
# =============================================================================
Write-Host "`n=== 3/3 FRONTEND ===" -ForegroundColor Cyan

if ($RebuildFrontend) {
    Write-Host "Rebuilding frontend with correct API URL: $BACKEND_URL" -ForegroundColor Yellow
    $frontendCtx = Read-Host "Path to frontend-context.tar.gz (or Enter to skip)"
    if ($frontendCtx -and (Test-Path $frontendCtx)) {
        Confirm-Step "Rebuild frontend image with NEXT_PUBLIC_API_URL=$BACKEND_URL?"
        az acr build `
            --registry $ACR_NAME `
            --resource-group $RESOURCE_GROUP `
            --image "synapse-frontend:${TAG}" `
            --file Dockerfile `
            --build-arg "NEXT_PUBLIC_API_URL=$BACKEND_URL" `
            --timeout 600 `
            $frontendCtx
        Write-Host "Frontend rebuilt!" -ForegroundColor Green
    }
}

Write-Host "Deploying Next.js frontend..." -ForegroundColor Gray
Write-Host "  Image:  ${ACR_SERVER}/synapse-frontend:${TAG}" -ForegroundColor Gray
Write-Host "  Port:   3000" -ForegroundColor Gray

Confirm-Step "Deploy Frontend container?"

az containerapp create `
    --name $FRONTEND_APP `
    --resource-group $RESOURCE_GROUP `
    --environment $ACA_ENV `
    --image "${ACR_SERVER}/synapse-frontend:${TAG}" `
    --registry-server $ACR_SERVER `
    --registry-username $ACR_USERNAME `
    --registry-password $ACR_PASSWORD `
    --target-port 3000 `
    --ingress "external" `
    --min-replicas 1 `
    --max-replicas 2 `
    --cpu 0.5 `
    --memory 1.0Gi `
    --output table

$FRONTEND_FQDN = (az containerapp show `
    --name $FRONTEND_APP `
    --resource-group $RESOURCE_GROUP `
    --query "properties.configuration.ingress.fqdn" `
    --output tsv)
$FRONTEND_URL = "https://$FRONTEND_FQDN"

# =============================================================================
# SUMMARY
# =============================================================================
Write-Host "`n" -NoNewline
Write-Host "================================================================" -ForegroundColor Green
Write-Host "  DEPLOYMENT COMPLETE" -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  FalkorDB (internal): $FALKORDB_FQDN" -ForegroundColor White
Write-Host "  Backend:             $BACKEND_URL" -ForegroundColor White
Write-Host "  Frontend:            $FRONTEND_URL" -ForegroundColor White
Write-Host ""
Write-Host "  --- Quick Commands ---" -ForegroundColor Cyan
Write-Host "  Health:     curl $BACKEND_URL/health" -ForegroundColor Gray
Write-Host "  BE logs:    az containerapp logs show -n $BACKEND_APP -g $RESOURCE_GROUP --follow" -ForegroundColor Gray
Write-Host "  FE logs:    az containerapp logs show -n $FRONTEND_APP -g $RESOURCE_GROUP --follow" -ForegroundColor Gray
Write-Host "  DB logs:    az containerapp logs show -n $FALKORDB_APP -g $RESOURCE_GROUP --follow" -ForegroundColor Gray
Write-Host ""
Write-Host "  --- Cleanup (removes EVERYTHING) ---" -ForegroundColor Cyan
Write-Host "  az group delete -n $RESOURCE_GROUP --yes" -ForegroundColor Gray
Write-Host ""

if (-not $RebuildFrontend) {
    Write-Host "  NOTE: Frontend was built with placeholder API URL." -ForegroundColor Yellow
    Write-Host "  To fix, re-run:" -ForegroundColor Yellow
    Write-Host "    .\4-deploy-apps.ps1 -RebuildFrontend" -ForegroundColor Yellow
    Write-Host ""
}

Write-Host "  Next step: ./5-migrate-data.sh on Mac (seed FalkorDB graph)" -ForegroundColor Cyan
