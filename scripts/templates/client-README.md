# SynapseOS — Product Advisor Platform

AI-powered product advisory system with Knowledge Graph reasoning, deployed on Azure Container Apps.

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Frontend    │────▶│  Backend    │────▶│  FalkorDB   │
│  (Next.js)  │     │  (FastAPI)  │     │  (Graph DB) │
│  port 3000  │     │  port 8000  │     │  port 6379  │
└─────────────┘     └─────────────┘     └─────────────┘
```

- **Frontend** — Next.js 14 React application
- **Backend** — FastAPI + Gemini LLM + Knowledge Graph reasoning engine
- **FalkorDB** — Graph database (Redis-compatible) with 4-layer knowledge graph

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (for building images)
- [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) (`az login`)
- [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.5

## Quick Start — Deploy to Azure

### 1. Create infrastructure

```bash
cd deploy/terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your secrets (API keys, passwords)

terraform init
terraform apply              # Phase 1: creates ACR, Storage, ACA Environment
```

### 2. Build & push Docker images

```bash
# Login to ACR (use the ACR name from terraform output)
az acr login --name <acr-name>

# Build backend (pre-compiled, runtime-only)
docker build --platform linux/amd64 \
  -t <acr-name>.azurecr.io/product-advisor-backend:v1 \
  backend/

# Build frontend (set API URL to your backend's FQDN)
docker build --platform linux/amd64 \
  --build-arg NEXT_PUBLIC_API_URL=https://<backend-fqdn> \
  -t <acr-name>.azurecr.io/product-advisor-frontend:v1 \
  frontend/

# Push
docker push <acr-name>.azurecr.io/product-advisor-backend:v1
docker push <acr-name>.azurecr.io/product-advisor-frontend:v1
```

### 3. Deploy apps + seed database

```bash
cd deploy/terraform

# Deploy Container Apps and seed FalkorDB (first time only)
terraform apply -var="deploy_apps=true" -var="seed_graph=true"
```

After seeding completes, subsequent deploys use just:
```bash
terraform apply -var="deploy_apps=true"
```

### 4. Update images

Bump the tag in `terraform.tfvars`:
```hcl
backend_image_tag  = "v2"
frontend_image_tag = "v2"
```
Then rebuild, push, and `terraform apply -var="deploy_apps=true"`.

## Directory Structure

```
├── backend/          Pre-compiled Python backend
│   ├── *.so          Compiled modules (background IP)
│   ├── *.py          Readable modules (foreground IP)
│   ├── tenants/      Domain configuration & prompts
│   └── Dockerfile    Runtime image (no compilation needed)
├── frontend/         Full Next.js source
│   └── Dockerfile    Multi-stage build
├── deploy/
│   └── terraform/    Azure Container Apps IaC
├── backups/          FalkorDB graph backup (Cypher)
└── docs/             Architecture documentation
```

## Environment Variables

See `deploy/terraform/terraform.tfvars.example` for the full list. Key secrets:

| Variable | Description |
|----------|-------------|
| `gemini_api_key` | Google Gemini API key (for LLM reasoning) |
| `openai_api_key` | OpenAI API key (for embeddings) |
| `falkordb_password` | FalkorDB Redis AUTH password |
| `jwt_secret_key` | JWT signing secret |

## Detailed Deployment Guide

See [deploy/terraform/README.md](deploy/terraform/README.md) for comprehensive step-by-step instructions, troubleshooting, and architecture details.
