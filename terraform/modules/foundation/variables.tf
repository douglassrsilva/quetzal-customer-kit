variable "catalog_name" {
  description = "Catálogo de Unity Catalog dedicado a Quetzal o autorizado para su uso."
  type        = string
}

variable "schema_name" {
  description = "Esquema de Unity Catalog dedicado a Quetzal."
  type        = string
  default     = "quetzal"
}

variable "create_catalog" {
  description = "Crea un catálogo dedicado. Use false para reutilizar un catálogo administrado por su organización."
  type        = bool
  default     = false
}

variable "create_groups" {
  description = "Crea grupos locales del workspace para usuarios y administradores de Quetzal."
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
  description = "Crea un SQL Warehouse serverless dedicado."
  type        = bool
  default     = true
}

variable "existing_warehouse_id" {
  description = "ID de un Warehouse existente cuando create_warehouse es false."
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
