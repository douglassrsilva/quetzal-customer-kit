variable "catalog_name" {
  description = "Unity Catalog catalog dedicated to or approved for Quetzal."
  type        = string
}

variable "schema_name" {
  description = "Unity Catalog schema dedicated to Quetzal."
  type        = string
  default     = "quetzal"
}

variable "create_catalog" {
  description = "Create a dedicated catalog. Set false to use a customer-managed catalog."
  type        = bool
  default     = false
}

variable "create_groups" {
  description = "Create workspace-local Quetzal user and admin groups."
  type        = bool
  default     = true
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
  description = "Create a dedicated serverless SQL warehouse."
  type        = bool
  default     = true
}

variable "existing_warehouse_id" {
  description = "Existing warehouse ID when create_warehouse is false."
  type        = string
  default     = null
  nullable    = true
}

variable "warehouse_name" {
  type    = string
  default = "Quetzal Serverless"
}

variable "warehouse_cluster_size" {
  type    = string
  default = "2X-Small"
}

variable "tags" {
  type    = map(string)
  default = {}
}
