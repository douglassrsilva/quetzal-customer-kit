# Databricks notebook source
# MAGIC %md
# MAGIC # Quetzal IQ · Managed Agent Memory
# MAGIC
# MAGIC Aprovisiona de forma idempotente el Memory Store gobernado y concede únicamente al
# MAGIC service principal de Databricks App permisos de lectura y escritura.

# COMMAND ----------

import json

from databricks.sdk import WorkspaceClient

dbutils.widgets.text("catalog", "")
dbutils.widgets.text("schema", "")
dbutils.widgets.text("memory_store", "quetzal_iq_memory")
dbutils.widgets.text("app_name", "")

catalog = dbutils.widgets.get("catalog").strip()
schema = dbutils.widgets.get("schema").strip()
store = dbutils.widgets.get("memory_store").strip()
app_name = dbutils.widgets.get("app_name").strip()
if not all((catalog, schema, store, app_name)):
    raise ValueError("catalog, schema, memory_store y app_name son obligatorios")
full_name = f"{catalog}.{schema}.{store}"
client = WorkspaceClient()
base_path = "/api/2.1/unity-catalog/memory-stores"

listed = client.api_client.do(
    "GET", base_path, query={"catalog_name": catalog, "schema_name": schema}
) or {}
stores = listed.get("memory_stores", listed.get("stores", [])) if isinstance(listed, dict) else listed
existing_names = {
    item.get("full_name") or ".".join(
        filter(None, [item.get("catalog_name"), item.get("schema_name"), item.get("name")])
    )
    for item in stores
}

if full_name in existing_names:
    action = "REUSED"
else:
    client.api_client.do(
        "POST",
        base_path,
        body={
            "name": store,
            "catalog_name": catalog,
            "schema_name": schema,
            "description": (
                "Memoria administrada de Quetzal IQ con alcance aislado por usuario. "
                "Guarda contexto de investigación externa y nunca almacena secretos."
            ),
        },
    )
    action = "CREATED"

verified = client.api_client.do("GET", f"{base_path}/{full_name}")
assert isinstance(verified, dict), verified

# El plano de control de Apps es la fuente confiable del ID del service principal.
app = client.api_client.do("GET", f"/api/2.0/apps/{app_name}")
principal = app.get("service_principal_client_id") or app.get("service_principal_name")
if not principal:
    raise AssertionError(f"No se encontró el service principal de la aplicación {app_name}")

permission_path = f"/api/2.1/unity-catalog/permissions/memory_store/{full_name}"
client.api_client.do(
    "PATCH",
    permission_path,
    body={
        "changes": [{
            "principal": principal,
            "add": ["READ_MEMORY_STORE", "WRITE_MEMORY_STORE"],
        }]
    },
)
permissions = client.api_client.do("GET", permission_path) or {}

print(json.dumps({
    "status": "PASSED",
    "action": action,
    "memory_store": full_name,
    "scope_strategy": "trusted authenticated Databricks Apps user",
    "app_principal": principal,
    "permission_assignments": len(permissions.get("privilege_assignments", [])),
}, ensure_ascii=False))
