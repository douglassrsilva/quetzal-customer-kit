module "foundation" {
  source = "../../modules/foundation"

  catalog_name          = var.catalog_name
  schema_name           = var.schema_name
  create_catalog        = var.create_catalog
  create_groups         = var.create_groups
  user_group_name       = var.user_group_name
  admin_group_name      = var.admin_group_name
  create_warehouse      = var.create_warehouse
  existing_warehouse_id = var.existing_warehouse_id
  tags                  = var.tags
}
