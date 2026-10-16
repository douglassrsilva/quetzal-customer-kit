output "bundle_values" {
  description = "Valores no secretos para copiar en config/customer.env."
  value = {
    catalog             = module.foundation.catalog_name
    schema              = module.foundation.schema_name
    sql_warehouse_id    = module.foundation.sql_warehouse_id
    app_user_group      = module.foundation.app_user_group
    quetzal_admin_group = module.foundation.admin_group
  }
}
