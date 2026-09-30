variable "databricks_host" {
  description = "Target Databricks workspace URL."
  type        = string
}

variable "databricks_profile" {
  description = "Local OAuth profile. CI should use workload identity environment variables instead."
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
