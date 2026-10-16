variable "databricks_host" {
  description = "URL del workspace de Databricks."
  type        = string
}

variable "databricks_profile" {
  description = "Perfil OAuth local. En CI, utilice variables de entorno con workload identity."
  type        = string
  default     = null
  nullable    = true
}

variable "catalog_name" {
  type = string
}

variable "schema_name" {
  type    = string
  default = "quetzal"
}

variable "create_catalog" {
  type    = bool
  default = false
}

variable "create_groups" {
  type    = bool
  default = true
}

variable "user_group_name" {
  type    = string
  default = "quetzal-users"
}

variable "admin_group_name" {
  type    = string
  default = "quetzal-admins"
}

variable "create_warehouse" {
  type    = bool
  default = true
}

variable "existing_warehouse_id" {
  type     = string
  default  = null
  nullable = true
}

variable "tags" {
  type    = map(string)
  default = {}
}
