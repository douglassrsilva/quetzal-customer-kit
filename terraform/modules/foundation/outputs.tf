output "catalog_name" {
  value = var.catalog_name
}

output "schema_name" {
  value = databricks_schema.quetzal.name
}

output "sql_warehouse_id" {
  value = var.create_warehouse ? databricks_sql_endpoint.quetzal[0].id : var.existing_warehouse_id
  precondition {
    condition     = var.create_warehouse || var.existing_warehouse_id != null
    error_message = "existing_warehouse_id es obligatorio cuando create_warehouse es false."
  }
}

output "app_user_group" {
  value = local.user_group
}

output "admin_group" {
  value = local.admin_group
}
