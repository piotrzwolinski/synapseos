# SynapseOS — Azure Deployment Guide (Portal + Terminal)

## Overview

| Step | Where       | What                                    |
|------|-------------|-----------------------------------------|
| 1    | **Portal**  | Create Resource Group                   |
| 2    | **Portal**  | Create Container Registry (ACR)         |
| 3    | **Portal**  | Create Storage Account + File Share     |
| 4    | **Portal**  | Create Container Apps Environment       |
| 5    | **Mac**     | Build Docker images / tar contexts      |
| 6    | **Windows** | Push images to ACR (terminal)           |
| 7    | **Portal**  | Create Container App: FalkorDB          |
| 8    | **Portal**  | Create Container App: Backend           |
| 9    | **Portal**  | Create Container App: Frontend          |

**Cleanup (if anything goes wrong):**
Portal → Resource Groups → `synapse-rg` → Delete resource group

---

## STEP 1: Create Resource Group

1. Portal → search **"Resource groups"** → **+ Create**
2. Fill in:
   - **Subscription**: (twoja subskrypcja)
   - **Resource group**: `synapse-rg`
   - **Region**: `West Europe`
3. Click **Review + create** → review → **Create**

---

## STEP 2: Create Container Registry (ACR)

1. Portal → search **"Container registries"** → **+ Create**
2. Fill in:
   - **Subscription**: (ta sama)
   - **Resource group**: `synapse-rg`
   - **Registry name**: `synapseosacr` (musi być globalnie unikalny, lowercase, bez myślników)
   - **Location**: `West Europe`
   - **SKU**: `Basic` (~$5/month)
3. Click **Review + create** → **Create**
4. After creation → go to the registry → **Settings** → **Access keys**:
   - Enable **Admin user** toggle
   - **SAVE these values** (you'll need them later):
     - Login server: `synapseosacr.azurecr.io`
     - Username: `synapseosacr`
     - Password: (copy the first password)

---

## STEP 3: Create Storage Account + File Share

### 3a: Storage Account

1. Portal → search **"Storage accounts"** → **+ Create**
2. Fill in:
   - **Resource group**: `synapse-rg`
   - **Storage account name**: `synapsestorage` (globalnie unikalny, lowercase)
   - **Region**: `West Europe`
   - **Performance**: `Standard`
   - **Redundancy**: `LRS` (Locally-redundant, najtańszy)
3. Click **Review + create** → **Create**

### 3b: File Share

1. Go to the created storage account
2. Left menu → **Data storage** → **File shares** → **+ File share**
3. Fill in:
   - **Name**: `falkordb-data`
   - **Tier**: `Transaction optimized`
   - **Quota**: `5` GiB (wystarczy na graph data)
4. Click **Create**
5. Go to storage account → **Security + networking** → **Access keys**
   - **SAVE the key1** (needed for step 4)

---

## STEP 4: Create Container Apps Environment

1. Portal → search **"Container Apps Environments"** → **+ Create**
2. Fill in:
   - **Resource group**: `synapse-rg`
   - **Environment name**: `synapse-env`
   - **Region**: `West Europe`
   - **Environment type**: `Workload profiles` (or Consumption if cheaper)
   - Leave **Log Analytics** as default (auto-creates)
3. Click **Review + create** → **Create**

### 4b: Add Azure Files storage to environment

1. Go to `synapse-env` container apps environment
2. Left menu → **Azure Files** → **+ Add**
3. Fill in:
   - **Name**: `falkordbstorage`
   - **Storage account name**: `synapsestorage`
   - **Storage account key**: (paste from step 3b)
   - **File share**: `falkordb-data`
   - **Access mode**: `ReadWrite`
4. Click **Add**

---

## STEP 5: Build Images on Mac

Run on your Mac terminal:

```bash
cd ~/projects/graph
chmod +x deploy/azure/2-build-contexts.sh

# If you have Docker Desktop:
./deploy/azure/2-build-contexts.sh --docker

# If you don't have Docker:
./deploy/azure/2-build-contexts.sh --tar
```

Then copy files from `deploy/azure/output/` to OneDrive.

---

## STEP 6: Push Images to ACR (Windows Terminal)

This is the ONLY step that requires Windows terminal.

### Pre-check: do you have Docker on Windows?

```powershell
docker --version
```

### If Docker exists → Path A:

```powershell
# Navigate to where you downloaded the files from OneDrive
cd C:\Users\YourName\Downloads  # or wherever

# Login to ACR
az login
az acr login --name synapseosacr

# Load and push backend
docker load -i backend-image.tar.gz
docker tag synapse-backend:latest synapseosacr.azurecr.io/synapse-backend:v1
docker push synapseosacr.azurecr.io/synapse-backend:v1

# Load and push frontend
docker load -i frontend-image.tar.gz
docker tag synapse-frontend:latest synapseosacr.azurecr.io/synapse-frontend:v1
docker push synapseosacr.azurecr.io/synapse-frontend:v1
```

### If no Docker → Path B:

```powershell
cd C:\Users\YourName\Downloads

az login

# Build backend in ACR (source on temp build agent, ~5 min)
az acr build --registry synapseosacr --resource-group synapse-rg --image synapse-backend:v1 --file Dockerfile.dist backend-context.tar.gz

# Build frontend in ACR
az acr build --registry synapseosacr --resource-group synapse-rg --image synapse-frontend:v1 --file Dockerfile --build-arg "NEXT_PUBLIC_API_URL=https://PLACEHOLDER" frontend-context.tar.gz
```

### Verify in Portal

Portal → Container registries → `synapseosacr` → **Repositories**
Should see:
- `synapse-backend` with tag `v1`
- `synapse-frontend` with tag `v1`

---

## STEP 7: Create Container App — FalkorDB

1. Portal → search **"Container Apps"** → **+ Create**
2. **Basics** tab:
   - **Resource group**: `synapse-rg`
   - **Container app name**: `synapse-falkordb`
   - **Container Apps Environment**: `synapse-env`
   - **Workload profile**: Consumption
3. **Container** tab:
   - Uncheck "Use quickstart image"
   - **Image source**: `Docker Hub or other registries`
   - **Image and tag**: `falkordb/falkordb:latest`
   - **CPU and Memory**: `1 vCPU, 2 GiB`
   - **Environment variables**:
     | Name | Source | Value |
     |------|--------|-------|
     | `REDIS_ARGS` | Manual entry | `--requirepass YOUR_STRONG_PASSWORD --save 60 1 --dir /data` |
   - **Volume mounts** → + Add:
     - Volume type: `Azure file volume`
     - Name: `falkordb-volume`
     - File share: `falkordbstorage`
     - Mount path: `/data`
4. **Ingress** tab:
   - Ingress: **Enabled**
   - Ingress traffic: **Limited to Container Apps Environment** (internal only!)
   - Ingress type: **TCP**
   - Target port: `6379`
5. **Review + create** → **Create**

**After creation, note the internal FQDN:**
Go to `synapse-falkordb` → Overview → **Application Url** (something like `synapse-falkordb.internal.<hash>.westeurope.azurecontainerapps.io`)

---

## STEP 8: Create Container App — Backend

1. Portal → **Container Apps** → **+ Create**
2. **Basics** tab:
   - **Resource group**: `synapse-rg`
   - **Container app name**: `synapse-backend`
   - **Container Apps Environment**: `synapse-env`
3. **Container** tab:
   - Uncheck "Use quickstart image"
   - **Image source**: `Azure Container Registry`
   - **Registry**: `synapseosacr.azurecr.io`
   - **Image**: `synapse-backend`
   - **Tag**: `v1`
   - **CPU and Memory**: `1 vCPU, 2 GiB`
   - **Environment variables**:
     | Name | Source | Value |
     |------|--------|-------|
     | `GEMINI_API_KEY` | Manual entry | `your-gemini-api-key` |
     | `FALKORDB_HOST` | Manual entry | `synapse-falkordb.internal.xxx.westeurope.azurecontainerapps.io` (FQDN from step 7) |
     | `FALKORDB_PORT` | Manual entry | `6379` |
     | `FALKORDB_PASSWORD` | Manual entry | `same-password-as-step-7` |
     | `FALKORDB_GRAPH` | Manual entry | `synapse` |
     | `DOMAIN_ID` | Manual entry | `mann_hummel` |
     | `JWT_SECRET_KEY` | Manual entry | `your-jwt-secret` |
     | `PYTHONUNBUFFERED` | Manual entry | `1` |
     | `AUTH_DISABLED` | Manual entry | `false` |
4. **Scale** tab:
   - Min replicas: `1`
   - Max replicas: `3`
5. **Ingress** tab:
   - Ingress: **Enabled**
   - Ingress traffic: **Accepting traffic from anywhere** (external)
   - Ingress type: **HTTP**
   - Target port: `8000`
6. **Review + create** → **Create**

**After creation:**
- Note the **Application URL** (e.g., `https://synapse-backend.<hash>.westeurope.azurecontainerapps.io`)
- Test: open `https://<backend-url>/health` in browser → should return `{"status": "healthy"}`
- If it doesn't work immediately, wait 1-2 minutes and check **Logs** in the portal

---

## STEP 9: Create Container App — Frontend

> **IMPORTANT**: Before this step, you need to rebuild the frontend image with the correct backend URL.
> Go back to Step 6 and rebuild using the actual backend URL from Step 8.
>
> **Path A (Docker on Windows):**
> On your Mac, rebuild:
> ```bash
> docker build --build-arg NEXT_PUBLIC_API_URL=https://synapse-backend.<hash>.westeurope.azurecontainerapps.io -f frontend/Dockerfile -t synapse-frontend frontend/
> docker save synapse-frontend:latest | gzip > deploy/azure/output/frontend-image.tar.gz
> ```
> Then transfer + push again.
>
> **Path B (az acr build):**
> ```powershell
> az acr build --registry synapseosacr --resource-group synapse-rg --image synapse-frontend:v1 --file Dockerfile --build-arg "NEXT_PUBLIC_API_URL=https://synapse-backend.<hash>.westeurope.azurecontainerapps.io" C:\path\to\frontend-context.tar.gz
> ```

1. Portal → **Container Apps** → **+ Create**
2. **Basics** tab:
   - **Resource group**: `synapse-rg`
   - **Container app name**: `synapse-frontend`
   - **Container Apps Environment**: `synapse-env`
3. **Container** tab:
   - Uncheck "Use quickstart image"
   - **Image source**: `Azure Container Registry`
   - **Registry**: `synapseosacr.azurecr.io`
   - **Image**: `synapse-frontend`
   - **Tag**: `v1`
   - **CPU and Memory**: `0.5 vCPU, 1 GiB`
4. **Scale** tab:
   - Min replicas: `1`
   - Max replicas: `2`
5. **Ingress** tab:
   - Ingress: **Enabled**
   - Ingress traffic: **Accepting traffic from anywhere** (external)
   - Ingress type: **HTTP**
   - Target port: `3000`
6. **Review + create** → **Create**

**After creation:**
Open the **Application URL** → SynapseOS UI should load!

---

## STEP 10: Verify & Seed Data

1. Open backend URL `/health` → should return `{"status": "healthy"}`
2. Open frontend URL → UI should load
3. Switch to **Graph Reasoning** mode (violet button)

### Seed FalkorDB (on Mac):

```bash
cd ~/projects/graph
./deploy/azure/5-migrate-data.sh --reseed
```

Or connect directly to the Azure FalkorDB from your graph-builder tools.

---

## Quick Reference

| Resource | Value |
|----------|-------|
| Resource Group | `synapse-rg` |
| ACR | `synapseosacr.azurecr.io` |
| Backend URL | `https://synapse-backend.<hash>.westeurope.azurecontainerapps.io` |
| Frontend URL | `https://synapse-frontend.<hash>.westeurope.azurecontainerapps.io` |
| FalkorDB (internal) | `synapse-falkordb.internal.<hash>.westeurope.azurecontainerapps.io:6379` |

## Troubleshooting

**Backend won't start:**
- Portal → synapse-backend → **Log stream** or **Console logs**
- Common issues: wrong FALKORDB_HOST, missing GEMINI_API_KEY

**Frontend shows blank page:**
- NEXT_PUBLIC_API_URL was not set correctly during build
- Rebuild frontend image with correct backend URL (see Step 9 note)

**FalkorDB connection refused:**
- Check that FALKORDB_HOST uses the FULL internal FQDN from step 7
- Check that FALKORDB_PASSWORD matches the REDIS_ARGS password

**Cleanup (remove everything):**
Portal → Resource Groups → `synapse-rg` → **Delete resource group** → type name → Delete
