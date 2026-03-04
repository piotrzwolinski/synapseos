# =============================================================================
# Step 1: Create Azure Infrastructure (INTERACTIVE — confirms each step)
# =============================================================================
# Run this on Windows App (PowerShell) after: az login
#
# Prerequisites:
#   - Azure CLI installed: winget install Microsoft.AzureCLI
#   - Logged in: az login
#   - Subscription selected: az account set --subscription "YOUR_SUB"
#
# Every step shows what it will do and asks for confirmation.
# Press Ctrl+C at any time to abort — nothing already created gets deleted,
# but you can clean up with: az group delete -n synapse-rg --yes
# =============================================================================

$ErrorActionPreference = "Stop"

# --- Configuration (edit these) ---
$RESOURCE_GROUP     = "synapse-rg"
$LOCATION           = "westeurope"
$ACR_NAME           = "synapseosacr"          # must be globally unique, lowercase, no hyphens
$STORAGE_ACCOUNT    = "synapsestorage"         # must be globally unique, lowercase, no hyphens
$FILESHARE_NAME     = "falkordb-data"
$ACA_ENV            = "synapse-env"
$FALKORDB_PASSWORD  = "CHANGE_ME_STRONG_PASSWORD"  # set a strong password

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

# =============================================================================
# PREFLIGHT: Show what subscription you're on
# =============================================================================
Write-Host "`n=== PREFLIGHT CHECK ===" -ForegroundColor Cyan
Write-Host "Checking Azure login..." -ForegroundColor Gray
try {
    $account = az account show --output json | ConvertFrom-Json
    Write-Host ""
    Write-Host "  Account:      $($account.user.name)" -ForegroundColor White
    Write-Host "  Subscription: $($account.name)" -ForegroundColor White
    Write-Host "  Sub ID:       $($account.id)" -ForegroundColor White
    Write-Host "  Tenant:       $($account.tenantId)" -ForegroundColor White
} catch {
    Write-Host "ERROR: Not logged in. Run 'az login' first." -ForegroundColor Red
    exit 1
}

Confirm-Step "Is this the correct subscription? (If not, run: az account set --subscription ""NAME"")"

# Show what will be created
Write-Host "`n=== PLAN: These resources will be CREATED ===" -ForegroundColor Cyan
Write-Host "  1. Resource Group:      $RESOURCE_GROUP (location: $LOCATION)" -ForegroundColor White
Write-Host "  2. Storage Account:     $STORAGE_ACCOUNT (Standard_LRS)" -ForegroundColor White
Write-Host "     + File Share:        $FILESHARE_NAME (5 GB quota)" -ForegroundColor White
Write-Host "  3. Container Registry:  $ACR_NAME (Basic SKU, ~$5/mo)" -ForegroundColor White
Write-Host "  4. Container Apps Env:  $ACA_ENV" -ForegroundColor White
Write-Host "  5. Storage mount in env (links file share to ACA)" -ForegroundColor White
Write-Host ""
Write-Host "  Estimated cost: ~$10-30/month (idle, before containers)" -ForegroundColor Gray
Write-Host "  Cleanup:  az group delete -n $RESOURCE_GROUP --yes" -ForegroundColor Gray

Confirm-Step "Create all the above resources?"

# =============================================================================
# 1. RESOURCE GROUP
# =============================================================================
Write-Host "`n=== 1/5 Resource Group ===" -ForegroundColor Cyan
Write-Host "Command: az group create --name $RESOURCE_GROUP --location $LOCATION" -ForegroundColor Gray

Confirm-Step "Create resource group '$RESOURCE_GROUP' in '$LOCATION'?"

az group create `
    --name $RESOURCE_GROUP `
    --location $LOCATION `
    --output table

Write-Host "Resource Group created." -ForegroundColor Green

# =============================================================================
# 2. STORAGE ACCOUNT + FILE SHARE
# =============================================================================
Write-Host "`n=== 2/5 Storage Account ===" -ForegroundColor Cyan
Write-Host "Purpose: Persistent storage for FalkorDB /data (graph database files)" -ForegroundColor Gray
Write-Host "Command: az storage account create --name $STORAGE_ACCOUNT --sku Standard_LRS" -ForegroundColor Gray

Confirm-Step "Create storage account '$STORAGE_ACCOUNT'?"

az storage account create `
    --name $STORAGE_ACCOUNT `
    --resource-group $RESOURCE_GROUP `
    --location $LOCATION `
    --sku Standard_LRS `
    --kind StorageV2 `
    --output table

Write-Host "Storage Account created." -ForegroundColor Green

Write-Host "`nGetting storage key..." -ForegroundColor Gray
$STORAGE_KEY = (az storage account keys list `
    --resource-group $RESOURCE_GROUP `
    --account-name $STORAGE_ACCOUNT `
    --query "[0].value" `
    --output tsv)

Write-Host "Creating file share: $FILESHARE_NAME (5 GB)..." -ForegroundColor Gray

az storage share-rm create `
    --storage-account $STORAGE_ACCOUNT `
    --resource-group $RESOURCE_GROUP `
    --name $FILESHARE_NAME `
    --quota 5 `
    --output table

Write-Host "File Share created." -ForegroundColor Green

# =============================================================================
# 3. CONTAINER REGISTRY
# =============================================================================
Write-Host "`n=== 3/5 Container Registry ===" -ForegroundColor Cyan
Write-Host "Purpose: Private Docker image storage (synapse-backend, synapse-frontend)" -ForegroundColor Gray
Write-Host "SKU: Basic (~$5/month, 10 GB storage)" -ForegroundColor Gray
Write-Host "Command: az acr create --name $ACR_NAME --sku Basic --admin-enabled true" -ForegroundColor Gray

Confirm-Step "Create container registry '$ACR_NAME'?"

az acr create `
    --resource-group $RESOURCE_GROUP `
    --name $ACR_NAME `
    --sku Basic `
    --admin-enabled true `
    --output table

$ACR_SERVER = "${ACR_NAME}.azurecr.io"
$ACR_USERNAME = (az acr credential show --name $ACR_NAME --query "username" --output tsv)
$ACR_PASSWORD = (az acr credential show --name $ACR_NAME --query "passwords[0].value" --output tsv)

Write-Host "Container Registry created." -ForegroundColor Green
Write-Host "  Server:   $ACR_SERVER" -ForegroundColor White
Write-Host "  Username: $ACR_USERNAME" -ForegroundColor White

# =============================================================================
# 4. CONTAINER APPS ENVIRONMENT
# =============================================================================
Write-Host "`n=== 4/5 Container Apps Environment ===" -ForegroundColor Cyan
Write-Host "Purpose: Shared network for all 3 containers (backend, frontend, falkordb)" -ForegroundColor Gray
Write-Host "This takes 1-2 minutes..." -ForegroundColor Gray
Write-Host "Command: az containerapp env create --name $ACA_ENV" -ForegroundColor Gray

Confirm-Step "Create Container Apps Environment '$ACA_ENV'?"

az containerapp env create `
    --name $ACA_ENV `
    --resource-group $RESOURCE_GROUP `
    --location $LOCATION `
    --output table

Write-Host "Container Apps Environment created." -ForegroundColor Green

# =============================================================================
# 5. MOUNT STORAGE TO ENVIRONMENT
# =============================================================================
Write-Host "`n=== 5/5 Mount Storage ===" -ForegroundColor Cyan
Write-Host "Purpose: Makes the Azure Files share available to FalkorDB container" -ForegroundColor Gray
Write-Host "Command: az containerapp env storage set --storage-name falkordbstorage" -ForegroundColor Gray

Confirm-Step "Mount file share to Container Apps Environment?"

az containerapp env storage set `
    --name $ACA_ENV `
    --resource-group $RESOURCE_GROUP `
    --storage-name falkordbstorage `
    --azure-file-account-name $STORAGE_ACCOUNT `
    --azure-file-account-key $STORAGE_KEY `
    --azure-file-share-name $FILESHARE_NAME `
    --access-mode ReadWrite `
    --output table

Write-Host "Storage mounted." -ForegroundColor Green

# =============================================================================
# SUMMARY
# =============================================================================
Write-Host "`n" -NoNewline
Write-Host "================================================================" -ForegroundColor Green
Write-Host "  SETUP COMPLETE — all 5 resources created" -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Resource Group:    $RESOURCE_GROUP"
Write-Host "  Location:          $LOCATION"
Write-Host "  ACR Server:        $ACR_SERVER"
Write-Host "  ACR Username:      $ACR_USERNAME"
Write-Host "  ACR Password:      $ACR_PASSWORD"
Write-Host "  Storage Account:   $STORAGE_ACCOUNT"
Write-Host "  File Share:        $FILESHARE_NAME"
Write-Host "  ACA Environment:   $ACA_ENV"
Write-Host ""
Write-Host "  SAVE THESE VALUES — you'll need them for steps 3 and 4!" -ForegroundColor Yellow
Write-Host ""
Write-Host "  To undo everything:" -ForegroundColor Gray
Write-Host "    az group delete -n $RESOURCE_GROUP --yes" -ForegroundColor Gray
Write-Host ""
Write-Host "  Next step: Run 2-build-contexts.sh on your Mac" -ForegroundColor Cyan
