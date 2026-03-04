# Product Advisor — Azure Container Apps Deployment Guide

> Deploys SynapseOS (FastAPI + Next.js + FalkorDB) to Azure Container Apps using Terraform.
> Backend uses Cython `.so` compilation — **no Python source code reaches Azure**.

## Architecture

```
Azure Resource Group: rg-codeit-product-advisor-poc-01 (pre-existing)
│
├── Azure Container Registry (ACR): crcodeitproductadvisorpoc01
│   ├── product-advisor-backend:v1   (Cython-compiled, no .py source)
│   └── product-advisor-frontend:v1  (Next.js standalone)
│
├── Container Apps Environment: cae-codeit-product-advisor-poc-01
│   ├── ca-backend-poc-01    (port 8000, external HTTPS)
│   ├── ca-frontend-poc-01   (port 3000, external HTTPS)
│   └── ca-falkordb-poc-01   (port 6379, INTERNAL TCP only)
│
├── Storage Account: stcodeitpocfalkordb01
│   └── Azure Files: falkordb-data  (mounted as /data in FalkorDB)
│
├── Log Analytics: log-codeit-product-advisor-poc-01
│
└── Storage Account: stcodeitpoctfstate01  (Terraform remote state)
```

## Constraints

- **No Azure CLI on Mac** — all Azure access through Windows App terminal / Cloud Shell
- **IP protection** — `backend/Dockerfile.dist` compiles Python to `.so` binaries
- **File transfer** — Mac → OneDrive → Windows App → Cloud Shell upload

## Quick Reference

| Command | What it does | Safe? |
|---------|-------------|-------|
| `terraform init` | Downloads providers, connects to state | Yes |
| `terraform plan` | Dry run — shows what would happen | Yes |
| `terraform apply` | Creates resources (prompts "yes") | Yes |
| `terraform apply -var="deploy_apps=true"` | Phase 2 — creates container apps | Yes |
| `terraform apply -var="deploy_apps=true" -var="seed_graph=true"` | Phase 2 + seed graph from backup | Yes |
| `terraform destroy` | Removes all TF-managed resources | Destructive |

---

## Prerequisites

- Azure Cloud Shell access (portal.azure.com → `>_` icon)
- Docker Desktop on Mac (for building images)
- OneDrive for file transfer Mac ↔ Windows

---

## Step 0: Create Terraform State Storage (one-time)

Execute the following in Cloud Shell:

```bash
az storage account create \
  --name stcodeitpoctfstate01 \
  --resource-group rg-codeit-product-advisor-poc-01 \
  --location westeurope \
  --sku Standard_LRS

az storage container create \
  --name tfstate \
  --account-name stcodeitpoctfstate01
```

---

## Step 1: Upload Terraform Files to Cloud Shell

Upload all `.tf` files + `terraform.tfvars` (see Step 2) via Cloud Shell upload button.

```bash
mkdir -p ~/product-advisor-tf && cd ~/product-advisor-tf
mv ~/*.tf ~/*.tfvars . 2>/dev/null
ls -la
```

> **Note**: Cloud Shell has a **100 MB upload limit** per file. Terraform configuration files are well within this limit. Image tarballs may require splitting (see Step 4).

---

## Step 2: Configure Secrets

```bash
cp terraform.tfvars.example terraform.tfvars
code terraform.tfvars   # Cloud Shell editor
```

Provide the following secrets:

| Variable | Description |
|----------|-------------|
| `gemini_api_key` | Google Gemini API key |
| `openai_api_key` | OpenAI API key (for vector embeddings) |
| `falkordb_password` | Strong password for FalkorDB Redis AUTH |
| `jwt_secret_key` | Random string for JWT signing |

All other variables have appropriate defaults.

---

## Step 3: Phase 1 — Create Infrastructure

```bash
cd ~/product-advisor-tf

terraform init
terraform plan          # always dry-run first
terraform apply         # type "yes" when prompted
```

Creates: ACR, Storage Account, Azure Files share, Log Analytics, ACA Environment, ACA storage mount.

Output:
```
acr_login_server = "crcodeitproductadvisorpoc01.azurecr.io"
```

---

## Step 4: Build Docker Images (Mac)

### Backend (Cython-compiled)

```bash
cd ~/projects/graph

# Required: --platform linux/amd64 (Apple Silicon builds ARM64; Azure requires AMD64)
docker build \
  --platform linux/amd64 \
  -f backend/Dockerfile.dist \
  -t product-advisor-backend:v1 \
  backend/

docker save product-advisor-backend:v1 | gzip > deploy/product-advisor-backend.tar.gz
```

### Frontend

```bash
# Placeholder URL — the image is rebuilt after the backend URL is known (Step 7)
docker build \
  --platform linux/amd64 \
  --build-arg NEXT_PUBLIC_API_URL=https://PLACEHOLDER \
  -t product-advisor-frontend:v1 \
  frontend/

docker save product-advisor-frontend:v1 | gzip > deploy/product-advisor-frontend.tar.gz
```

### Cloud Shell 100 MB Upload Limit

If the backend tarball exceeds 100 MB, split it into smaller parts:

```bash
# Split on Mac into 90 MB parts
split -b 90m deploy/product-advisor-backend.tar.gz deploy/backend-part-

# In Cloud Shell, reassemble the parts
cat backend-part-* > product-advisor-backend.tar.gz
```

Transfer the tarball files via **OneDrive → Windows App → Cloud Shell upload**.

---

## Step 5: Push Images to ACR (Cloud Shell)

Azure Cloud Shell does not include a Docker daemon. Use **regctl** to push image tarballs directly to ACR.

### Install regctl

```bash
curl -fLo regctl "https://github.com/regclient/regclient/releases/download/v0.8.3/regctl-linux-amd64"
chmod +x regctl
```

> **Important**: Do not use the GitHub `/releases/latest/download/` URL. The redirect may return HTML instead of the binary. Always use an explicit version URL as shown above.

### Push to ACR

```bash
ACR=crcodeitproductadvisorpoc01.azurecr.io
ACR_USER=$(az acr credential show --name crcodeitproductadvisorpoc01 --query username -o tsv)
ACR_PASS=$(az acr credential show --name crcodeitproductadvisorpoc01 --query "passwords[0].value" -o tsv)

# Login
./regctl registry login "$ACR" -u "$ACR_USER" -p "$ACR_PASS"

# Import + push backend
./regctl image import "ocidir://backend-oci:v1" product-advisor-backend.tar.gz
./regctl image copy "ocidir://backend-oci:v1" "$ACR/product-advisor-backend:v1"

# Import + push frontend
./regctl image import "ocidir://frontend-oci:v1" product-advisor-frontend.tar.gz
./regctl image copy "ocidir://frontend-oci:v1" "$ACR/product-advisor-frontend:v1"

# Verify
az acr repository list --name crcodeitproductadvisorpoc01 -o table
```

---

## Step 6: Phase 2 — Deploy Apps + Seed Graph

### Option A: Deploy + seed in one command (first deploy)

Ensure `seed_from_backup.sh` is located alongside the `.tf` files in Cloud Shell, then execute:

```bash
cd ~/product-advisor-tf

terraform plan  -var="deploy_apps=true" -var="seed_graph=true"
terraform apply -var="deploy_apps=true" -var="seed_graph=true"
```

This will:
1. Create all 3 container apps
2. Upload `seed_from_backup.sh` to Azure Files (mounted as `/data`)
3. Wait for FalkorDB to start
4. Execute the seed script (3636 Cypher statements)
5. Create the vector index (dimension 3072)

> **Note**: The seed provisioner only runs on **first create**. On subsequent `terraform apply` runs it won't re-seed (safe to leave `seed_graph=true`).

### Option B: Deploy without seeding

```bash
terraform apply -var="deploy_apps=true"
```

Seed the database manually afterwards (see [Manual Seeding](#manual-seeding)).

### Output

```
backend_url  = "https://ca-backend-poc-01.<env-hash>.westeurope.azurecontainerapps.io"
frontend_url = "https://ca-frontend-poc-01.<env-hash>.westeurope.azurecontainerapps.io"
```

Record the output URLs for subsequent steps.

### Generating seed_from_backup.sh

If the seed script is not yet available, generate it on Mac:

```bash
cd ~/projects/graph

python3 -c "
lines = open('backups/synapse_backup_YYYYMMDD_HHMMSS.cypher').readlines()
for l in lines:
    l = l.strip()
    if l and not l.startswith('//'):
        escaped = l.replace(\"'\", \"'\\\\''\")
        print(f\"redis-cli -a \\\$FALKORDB_PASSWORD GRAPH.QUERY synapse '{escaped}'\")
" > deploy/terraform/seed_from_backup.sh
```

---

## Step 7: Rebuild Frontend with Real Backend URL

```bash
# On Mac — rebuild with actual backend URL
docker build \
  --platform linux/amd64 \
  --build-arg NEXT_PUBLIC_API_URL=https://ca-backend-poc-01.<env-hash>.westeurope.azurecontainerapps.io \
  -t product-advisor-frontend:v1 \
  frontend/

docker save product-advisor-frontend:v1 | gzip > deploy/product-advisor-frontend.tar.gz
```

Upload the tarball to Cloud Shell and push to ACR using the same regctl commands from Step 5 (frontend only).

Restart the frontend container to load the updated image:

```bash
az containerapp revision restart \
  --name ca-frontend-poc-01 \
  --resource-group rg-codeit-product-advisor-poc-01
```

---

## Step 8: Verify

1. Health check:
   ```
   curl https://<backend-url>/health
   # → {"status": "healthy"}
   ```

2. Open `https://<frontend-url>` — UI should load

3. Switch to **Graph Reasoning** mode (violet button in top bar)

4. Send a test query — reasoning chain + response should appear

---

## Updating Images

```bash
# Update image tag via Terraform variable
terraform apply -var="deploy_apps=true" -var="backend_image_tag=v2"
```

Alternatively, update the container directly:

```bash
az containerapp update \
  --name ca-backend-poc-01 \
  --resource-group rg-codeit-product-advisor-poc-01 \
  --image crcodeitproductadvisorpoc01.azurecr.io/product-advisor-backend:v2
```

---

## Environment Variables Reference

### Backend (ca-backend-poc-01)

| Variable | Source | Description |
|----------|--------|-------------|
| `GEMINI_API_KEY` | Secret | Google Gemini API key |
| `OPENAI_API_KEY` | Secret | OpenAI API key (embeddings) |
| `FALKORDB_HOST` | Env | `ca-falkordb-poc-01` (short hostname, not FQDN) |
| `FALKORDB_PORT` | Env | `6379` |
| `FALKORDB_PASSWORD` | Secret | FalkorDB Redis AUTH |
| `FALKORDB_GRAPH` | Env | `synapse` |
| `DOMAIN_ID` | Env | `mann_hummel` |
| `JWT_SECRET_KEY` | Secret | JWT signing secret |
| `PYTHONUNBUFFERED` | Env | `1` (prevents log buffering) |
| `AUTH_DISABLED` | Env | `false` |

### Frontend (ca-frontend-poc-01)

| Variable | Source | Description |
|----------|--------|-------------|
| `NEXT_PUBLIC_API_URL` | Build ARG | Backend HTTPS URL (baked at build time) |

### FalkorDB (ca-falkordb-poc-01)

| Variable | Source | Description |
|----------|--------|-------------|
| `REDIS_ARGS` | Env | `--requirepass <password> --save 60 1 --dir /data` |

---

## Terraform Files

| File | Purpose |
|------|---------|
| `main.tf` | All Azure resources (ACR, Storage, ACA Environment, 3 Container Apps, graph seed) |
| `variables.tf` | Variable declarations with defaults |
| `providers.tf` | Azure provider config + remote state backend |
| `outputs.tf` | URLs and helper commands shown after apply |
| `terraform.tfvars.example` | Template for secrets (copy to `.tfvars`) |
| `seed_from_backup.sh` | Graph seed script (generated from Cypher backup, needed for `seed_graph=true`) |
| `.gitignore` | Excludes `.terraform/`, `*.tfstate`, `*.tfvars` |

---

## Cleanup

```bash
terraform destroy   # Removes all Terraform-managed resources
# The Resource Group is retained (created by IT, not managed by Terraform)
```

---

## Manual Seeding

If the deployment was performed without `seed_graph=true`, the graph database must be seeded manually:

```bash
# 1. Upload seed script to Azure Files
az storage file upload \
  --account-name stcodeitpocfalkordb01 \
  --share-name falkordb-data \
  --source seed_from_backup.sh \
  --path seed_from_backup.sh

# 2. Execute inside FalkorDB container
az containerapp exec \
  --name ca-falkordb-poc-01 \
  --resource-group rg-codeit-product-advisor-poc-01 \
  --command "bash /data/seed_from_backup.sh"

# 3. Create vector index (dimension 3072 for OpenAI text-embedding-3-large)
az containerapp exec \
  --name ca-falkordb-poc-01 \
  --resource-group rg-codeit-product-advisor-poc-01 \
  --command "redis-cli -a YOUR_FALKORDB_PASSWORD GRAPH.QUERY synapse 'CREATE VECTOR INDEX FOR (c:Concept) ON (c.embedding) OPTIONS {dimension: 3072}'"
```

---

## Troubleshooting

### Common Issues

| Problem | Root Cause | Fix |
|---------|-----------|-----|
| `no child with platform linux/amd64` | Built on Apple Silicon (ARM64) | Rebuild with `--platform linux/amd64` |
| `already exists` after failed deploy | Container app in Failed state, not in TF state | `az containerapp delete --name <name> -g <rg> --yes` then re-apply |
| FalkorDB connection timeout | `exposed_port` not set on TCP ingress | Ensure `exposed_port = 6379` in `main.tf` ingress block |
| FalkorDB FQDN times out | ACA internal TCP uses short hostnames | Set `FALKORDB_HOST=ca-falkordb-poc-01` (no `.internal...` suffix) |
| `Invalid arguments for procedure db.idx.vector.queryNodes` | Vector index missing | Run `CREATE VECTOR INDEX` (see [Manual Seeding](#manual-seeding)) |
| `Vector dimension mismatch` | Index created with wrong dimension | Drop index, recreate with `dimension: 3072` |
| `OPENAI_API_KEY not set` | Missing env var in backend | Add `openai-api-key` secret + env var |
| Backend crash loop | Check Log Analytics for actual error | Portal → Container App → Log stream |
| Frontend blank page | `NEXT_PUBLIC_API_URL` wrong or missing | Rebuild frontend image with correct backend URL |
| Cloud Shell upload fails (>100MB) | 100 MB per-file limit | Split with `split -b 90m`, reassemble with `cat` |
| regctl downloads HTML, not binary | GitHub redirect issue | Use explicit version URL, not `/latest/download/` |
| `terraform init` fails | State storage not created | Run Step 0 first |
| Permission denied | Wrong subscription | `az account set --subscription fb01fd65-...` |

### Diagnostic Commands

```bash
# Stream container app logs
az containerapp logs show \
  --name ca-backend-poc-01 \
  --resource-group rg-codeit-product-advisor-poc-01 \
  --follow

# View system-level logs
az containerapp logs show \
  --name ca-backend-poc-01 \
  --resource-group rg-codeit-product-advisor-poc-01 \
  --type system

# Verify FalkorDB connectivity
az containerapp exec \
  --name ca-falkordb-poc-01 \
  --resource-group rg-codeit-product-advisor-poc-01 \
  --command "redis-cli -a YOUR_PASSWORD PING"

# Query container app provisioning status
az containerapp show \
  --name ca-backend-poc-01 \
  --resource-group rg-codeit-product-advisor-poc-01 \
  --query "{status:properties.provisioningState, latestRevision:properties.latestRevisionName}"

# List repositories in ACR
az acr repository list --name crcodeitproductadvisorpoc01 -o table

# Inspect FalkorDB ingress configuration
az containerapp ingress show \
  --name ca-falkordb-poc-01 \
  --resource-group rg-codeit-product-advisor-poc-01
```

### ACA Internal TCP Networking

Azure Container Apps internal TCP ingress has two non-obvious requirements:

1. The `exposed_port` property **must** be set explicitly for TCP transport. HTTP ingress does not require this.
2. Container-to-container communication within the same environment requires **short hostnames** (`ca-falkordb-poc-01`), not the full FQDN (`ca-falkordb-poc-01.internal.xxx.azurecontainerapps.io`).

Both issues are addressed in the current Terraform configuration.
