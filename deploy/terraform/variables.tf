# =============================================================================
# Variables — edit values in terraform.tfvars (NOT here)
# =============================================================================

# --- Azure basics ---

variable "subscription_id" {
  description = "Azure subscription ID"
  type        = string
  default     = "fb01fd65-839e-4a89-9b61-5317cf61e941"
}

variable "location" {
  description = "Azure region"
  type        = string
  default     = "westeurope"
}

variable "resource_group_name" {
  description = "Name of the EXISTING resource group (created by client IT)"
  type        = string
  default     = "rg-codeit-product-advisor-poc-01"
}

# --- Naming ---

variable "acr_name" {
  description = "Container Registry name (globally unique, lowercase, no hyphens)"
  type        = string
  default     = "crcodeitproductadvisorpoc01"
}

variable "storage_account_name" {
  description = "Storage account name (globally unique, lowercase, no hyphens)"
  type        = string
  default     = "stcodeitpocfalkordb01"
}

# --- Image tags ---

variable "backend_image_tag" {
  description = "Backend image tag in ACR"
  type        = string
  default     = "v1"
}

variable "frontend_image_tag" {
  description = "Frontend image tag in ACR"
  type        = string
  default     = "v1"
}

# --- Secrets ---

variable "gemini_api_key" {
  description = "Google Gemini API key"
  type        = string
  sensitive   = true
}

variable "falkordb_password" {
  description = "Password for FalkorDB (Redis AUTH)"
  type        = string
  sensitive   = true
}

variable "jwt_secret_key" {
  description = "JWT signing secret"
  type        = string
  sensitive   = true
}

variable "openai_api_key" {
  description = "OpenAI API key (for embeddings)"
  type        = string
  sensitive   = true
}

# --- App config ---

variable "domain_id" {
  description = "Tenant domain ID"
  type        = string
  default     = "mann_hummel"
}

variable "frontend_api_url" {
  description = "Backend URL for frontend (set after first apply, then re-apply)"
  type        = string
  default     = ""
}

# --- Deploy control ---

variable "deploy_apps" {
  description = "Set to true AFTER images are pushed to ACR. First run: false (infra only)."
  type        = bool
  default     = false
}

variable "seed_graph" {
  description = "Set to true on FIRST deploy to seed FalkorDB from backup. Requires seed_from_backup.sh next to .tf files. Only runs once (on create)."
  type        = bool
  default     = false
}
