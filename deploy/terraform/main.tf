# =============================================================================
# SynapseOS — Azure Container Apps Infrastructure
# =============================================================================
#
# Uses EXISTING resource group: rg-codeit-product-advisor-poc-01
# Subscription: sub-sandbox-dev-01
#
# Phase 1 (deploy_apps = false):  Creates infra only (ACR, Storage, ACA Env)
# Phase 2 (deploy_apps = true):   Also creates 3 Container Apps
# Phase 2 + seed (seed_graph = true): Also seeds FalkorDB from backup + creates vector index
#
# Usage:
#   terraform plan                            # dry-run — see what will happen
#   terraform apply                           # phase 1: infra
#   <push images to ACR>
#   terraform apply -var="deploy_apps=true"                          # phase 2: apps only
#   terraform apply -var="deploy_apps=true" -var="seed_graph=true"   # phase 2: apps + seed
#
# Cleanup:
#   terraform destroy    # removes everything INSIDE the RG (not the RG itself)
# =============================================================================

# --- Existing Resource Group (created by client IT) ---

data "azurerm_resource_group" "main" {
  name = var.resource_group_name
}

locals {
  tags = {
    project     = "product-advisor"
    environment = "poc"
    managed_by  = "terraform"
  }
}

# --- Container Registry (ACR) ---

resource "azurerm_container_registry" "acr" {
  name                = var.acr_name
  resource_group_name = data.azurerm_resource_group.main.name
  location            = data.azurerm_resource_group.main.location
  sku                 = "Basic"
  admin_enabled       = true

  tags = local.tags
}

# --- Storage Account + File Share (FalkorDB persistence) ---

resource "azurerm_storage_account" "main" {
  name                     = var.storage_account_name
  resource_group_name      = data.azurerm_resource_group.main.name
  location                 = data.azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "LRS"

  tags = local.tags
}

resource "azurerm_storage_share" "falkordb" {
  name               = "falkordb-data"
  storage_account_id = azurerm_storage_account.main.id
  quota              = 5
}

# --- Log Analytics Workspace (required by ACA) ---

resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-codeit-product-advisor-poc-01"
  resource_group_name = data.azurerm_resource_group.main.name
  location            = data.azurerm_resource_group.main.location
  sku                 = "PerGB2018"
  retention_in_days   = 30

  tags = local.tags
}

# --- Container Apps Environment ---

resource "azurerm_container_app_environment" "main" {
  name                       = "cae-codeit-product-advisor-poc-01"
  resource_group_name        = data.azurerm_resource_group.main.name
  location                   = data.azurerm_resource_group.main.location
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id

  tags = local.tags
}

# --- Mount Azure Files to Environment ---

resource "azurerm_container_app_environment_storage" "falkordb" {
  name                         = "falkordbstorage"
  container_app_environment_id = azurerm_container_app_environment.main.id
  account_name                 = azurerm_storage_account.main.name
  access_key                   = azurerm_storage_account.main.primary_access_key
  share_name                   = azurerm_storage_share.falkordb.name
  access_mode                  = "ReadWrite"
}

# =============================================================================
# Container Apps (only created when deploy_apps = true)
# =============================================================================

# --- FalkorDB (internal, with persistent storage) ---

resource "azurerm_container_app" "falkordb" {
  count = var.deploy_apps ? 1 : 0

  name                         = "ca-falkordb-poc-01"
  resource_group_name          = data.azurerm_resource_group.main.name
  container_app_environment_id = azurerm_container_app_environment.main.id
  revision_mode                = "Single"

  template {
    min_replicas = 1
    max_replicas = 1

    container {
      name   = "falkordb"
      image  = "falkordb/falkordb:latest"
      cpu    = 1.0
      memory = "2Gi"

      env {
        name  = "REDIS_ARGS"
        value = "--requirepass ${var.falkordb_password} --save 60 1 --dir /data"
      }

      volume_mounts {
        name = "falkordb-volume"
        path = "/data"
      }
    }

    volume {
      name         = "falkordb-volume"
      storage_name = azurerm_container_app_environment_storage.falkordb.name
      storage_type = "AzureFile"
    }
  }

  ingress {
    external_enabled = false
    target_port      = 6379
    exposed_port     = 6379
    transport        = "tcp"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  tags = local.tags
}

# --- Graph Seed: upload script to Azure Files (mounted as /data) ---

resource "azurerm_storage_share_file" "seed_script" {
  count            = var.deploy_apps && var.seed_graph ? 1 : 0
  name             = "seed_from_backup.sh"
  storage_share_id = azurerm_storage_share.falkordb.id
  source           = "${path.module}/seed_from_backup.sh"
}

# --- Graph Seed: execute seed script + create vector index ---

resource "terraform_data" "graph_seed" {
  count = var.deploy_apps && var.seed_graph ? 1 : 0

  depends_on = [
    azurerm_container_app.falkordb,
    azurerm_storage_share_file.seed_script,
  ]

  provisioner "local-exec" {
    command = <<-EOT
      echo "⏳ Waiting 30s for FalkorDB to start..."
      sleep 30

      echo "📦 Seeding graph from backup..."
      az containerapp exec \
        --name ca-falkordb-poc-01 \
        --resource-group ${var.resource_group_name} \
        --command "bash /data/seed_from_backup.sh"

      echo "🔍 Creating vector index (dim 3072)..."
      az containerapp exec \
        --name ca-falkordb-poc-01 \
        --resource-group ${var.resource_group_name} \
        --command "redis-cli -a '${var.falkordb_password}' GRAPH.QUERY synapse 'CREATE VECTOR INDEX FOR (c:Concept) ON (c.embedding) OPTIONS {dimension: 3072}'"

      echo "✅ Graph seeding complete!"
    EOT
  }
}

# --- Backend (external, connects to FalkorDB) ---

resource "azurerm_container_app" "backend" {
  count = var.deploy_apps ? 1 : 0

  name                         = "ca-backend-poc-01"
  resource_group_name          = data.azurerm_resource_group.main.name
  container_app_environment_id = azurerm_container_app_environment.main.id
  revision_mode                = "Single"

  registry {
    server               = azurerm_container_registry.acr.login_server
    username             = azurerm_container_registry.acr.admin_username
    password_secret_name = "acr-password"
  }

  secret {
    name  = "acr-password"
    value = azurerm_container_registry.acr.admin_password
  }

  secret {
    name  = "gemini-api-key"
    value = var.gemini_api_key
  }

  secret {
    name  = "falkordb-password"
    value = var.falkordb_password
  }

  secret {
    name  = "jwt-secret-key"
    value = var.jwt_secret_key
  }

  secret {
    name  = "openai-api-key"
    value = var.openai_api_key
  }

  template {
    min_replicas = 1
    max_replicas = 3

    container {
      name   = "backend"
      image  = "${azurerm_container_registry.acr.login_server}/product-advisor-backend:${var.backend_image_tag}"
      cpu    = 1.0
      memory = "2Gi"

      env {
        name        = "GEMINI_API_KEY"
        secret_name = "gemini-api-key"
      }

      env {
        name  = "FALKORDB_HOST"
        value = "ca-falkordb-poc-01"
      }

      env {
        name  = "FALKORDB_PORT"
        value = "6379"
      }

      env {
        name        = "FALKORDB_PASSWORD"
        secret_name = "falkordb-password"
      }

      env {
        name  = "FALKORDB_GRAPH"
        value = "synapse"
      }

      env {
        name  = "DOMAIN_ID"
        value = var.domain_id
      }

      env {
        name        = "JWT_SECRET_KEY"
        secret_name = "jwt-secret-key"
      }

      env {
        name        = "OPENAI_API_KEY"
        secret_name = "openai-api-key"
      }

      env {
        name  = "PYTHONUNBUFFERED"
        value = "1"
      }

      env {
        name  = "AUTH_DISABLED"
        value = "false"
      }
    }
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    transport        = "http"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  tags = local.tags
}

# --- Frontend (external) ---

resource "azurerm_container_app" "frontend" {
  count = var.deploy_apps ? 1 : 0

  name                         = "ca-frontend-poc-01"
  resource_group_name          = data.azurerm_resource_group.main.name
  container_app_environment_id = azurerm_container_app_environment.main.id
  revision_mode                = "Single"

  registry {
    server               = azurerm_container_registry.acr.login_server
    username             = azurerm_container_registry.acr.admin_username
    password_secret_name = "acr-password"
  }

  secret {
    name  = "acr-password"
    value = azurerm_container_registry.acr.admin_password
  }

  template {
    min_replicas = 1
    max_replicas = 2

    container {
      name   = "frontend"
      image  = "${azurerm_container_registry.acr.login_server}/product-advisor-frontend:${var.frontend_image_tag}"
      cpu    = 0.5
      memory = "1Gi"
    }
  }

  ingress {
    external_enabled = true
    target_port      = 3000
    transport        = "http"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  tags = local.tags
}
