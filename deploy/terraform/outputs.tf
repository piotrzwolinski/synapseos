# =============================================================================
# Outputs — shown after terraform apply
# =============================================================================

# --- Always available (Phase 1) ---

output "resource_group" {
  value = data.azurerm_resource_group.main.name
}

output "acr_login_server" {
  value = azurerm_container_registry.acr.login_server
}

output "acr_admin_username" {
  value = azurerm_container_registry.acr.admin_username
}

output "acr_admin_password" {
  value     = azurerm_container_registry.acr.admin_password
  sensitive = true
}

output "push_commands" {
  value = <<-EOT

    === NEXT: Push images to ACR (run in Cloud Shell) ===

    # 1. Login to ACR
    az acr login --name ${var.acr_name}

    # 2. Upload tar files (use Cloud Shell upload button)

    # 3a. If backend-context.tar.gz (Path B):
    az acr build --registry ${var.acr_name} -g ${var.resource_group_name} --image synapse-backend:${var.backend_image_tag} --file Dockerfile.dist backend-context.tar.gz

    # 3b. If frontend-context.tar.gz (Path B):
    az acr build --registry ${var.acr_name} -g ${var.resource_group_name} --image synapse-frontend:${var.frontend_image_tag} --file Dockerfile --build-arg "NEXT_PUBLIC_API_URL=<BACKEND_URL>" frontend-context.tar.gz

    # 4. Then deploy apps:
    terraform apply -var="deploy_apps=true"

  EOT
}

# --- Available after Phase 2 (deploy_apps = true) ---

output "falkordb_fqdn" {
  value = var.deploy_apps ? azurerm_container_app.falkordb[0].ingress[0].fqdn : "(deploy_apps = false)"
}

output "backend_url" {
  value = var.deploy_apps ? "https://${azurerm_container_app.backend[0].ingress[0].fqdn}" : "(deploy_apps = false)"
}

output "frontend_url" {
  value = var.deploy_apps ? "https://${azurerm_container_app.frontend[0].ingress[0].fqdn}" : "(deploy_apps = false)"
}

output "cleanup_command" {
  value = "terraform destroy"
}
