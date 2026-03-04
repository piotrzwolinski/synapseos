terraform {
  required_version = ">= 1.5"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }

  # Remote state in Azure Storage.
  # Create the storage container FIRST (see README.md step 0).
  backend "azurerm" {
    resource_group_name  = "rg-codeit-product-advisor-poc-01"
    storage_account_name = "stcodeitpoctfstate01" # create this in step 0
    container_name       = "tfstate"
    key                  = "synapse.terraform.tfstate"
  }
}

provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
}
