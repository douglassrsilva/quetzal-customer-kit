resource "databricks_group" "users" {
  count        = var.create_groups ? 1 : 0
  display_name = var.user_group_name
}

resource "databricks_group" "admins" {
  count        = var.create_groups ? 1 : 0
  display_name = var.admin_group_name
}

locals {
  user_group  = var.create_groups ? databricks_group.users[0].display_name : var.user_group_name
  admin_group = var.create_groups ? databricks_group.admins[0].display_name : var.admin_group_name
}

resource "databricks_catalog" "quetzal" {
  count          = var.create_catalog ? 1 : 0
  name           = var.catalog_name
  comment        = "Catálogo para la inteligencia de telecomunicaciones de Quetzal"
  isolation_mode = "ISOLATED"
  owner          = local.admin_group
  properties = merge(var.tags, {
    managed_by          = "terraform"
    data_classification = "customer-controlled"
    product             = "quetzal"
  })
  lifecycle {
    prevent_destroy = true
  }
}

resource "databricks_schema" "quetzal" {
  catalog_name = var.create_catalog ? databricks_catalog.quetzal[0].name : var.catalog_name
  name         = var.schema_name
  comment      = "Modelo de datos canónico y operativo de Quetzal"
  owner        = local.admin_group
  properties = merge(var.tags, {
    managed_by = "terraform"
    product    = "quetzal"
  })
  lifecycle {
    prevent_destroy = true
  }
}

resource "databricks_grant" "catalog_users" {
  catalog    = var.catalog_name
  principal  = local.user_group
  privileges = ["USE_CATALOG"]
  depends_on = [databricks_schema.quetzal]
}

resource "databricks_grant" "catalog_admins" {
  catalog    = var.catalog_name
  principal  = local.admin_group
  privileges = ["USE_CATALOG"]
  depends_on = [databricks_schema.quetzal]
}

resource "databricks_grant" "schema_users" {
  schema     = "${var.catalog_name}.${var.schema_name}"
  principal  = local.user_group
  privileges = ["USE_SCHEMA", "SELECT", "EXECUTE"]
  depends_on = [databricks_schema.quetzal]
}

resource "databricks_grant" "schema_admins" {
  schema    = "${var.catalog_name}.${var.schema_name}"
  principal = local.admin_group
  privileges = [
    "USE_SCHEMA",
    "CREATE_TABLE",
    "CREATE_FUNCTION",
    "EXECUTE",
    "MODIFY",
    "SELECT",
  ]
  depends_on = [databricks_schema.quetzal]
}

resource "databricks_sql_endpoint" "quetzal" {
  count                     = var.create_warehouse ? 1 : 0
  name                      = var.warehouse_name
  cluster_size              = var.warehouse_cluster_size
  auto_stop_mins            = 10
  enable_serverless_compute = true
  warehouse_type            = "PRO"
  max_num_clusters          = 1
  min_num_clusters          = 1
  tags {
    dynamic "custom_tags" {
      for_each = merge(var.tags, {
        managed_by = "terraform"
        product    = "quetzal"
      })
      content {
        key   = custom_tags.key
        value = custom_tags.value
      }
    }
  }
}

resource "databricks_permissions" "warehouse" {
  count           = var.create_warehouse ? 1 : 0
  sql_endpoint_id = databricks_sql_endpoint.quetzal[0].id

  access_control {
    group_name       = local.user_group
    permission_level = "CAN_USE"
  }

  access_control {
    group_name       = local.admin_group
    permission_level = "CAN_MANAGE"
  }
}
