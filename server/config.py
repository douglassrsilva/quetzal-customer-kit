"""Configuración de Quetzal mediante variables de entorno.

Databricks Apps agrega las variables de autenticación durante la ejecución. Los
identificadores de recursos permanecen configurables para promover el mismo código
entre entornos sin editar archivos Python.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

COUNTRIES = ("PA", "MX", "CO", "BR", "AR", "CL", "PE", "EC", "CR", "GT", "DO", "UY")


def _host(value: str) -> str:
    value = value.strip().rstrip("/")
    if value and not value.startswith(("http://", "https://")):
        value = f"https://{value}"
    return value


def _optional_url(value: str) -> str:
    return "" if value.strip().upper() in {"", "DISABLED", "NONE"} else _host(value)


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} debe ser un entero") from exc
    if value <= 0:
        raise RuntimeError(f"{name} debe ser mayor que cero")
    return value


@dataclass(frozen=True)
class Settings:
    catalog: str
    schema: str
    host: str
    warehouse_id: str
    workspace_id: str
    dashboard_id: str
    ai_model: str
    ai_url: str
    genie_ingresos_id: str
    genie_clientes_id: str
    genie_red_id: str
    graph_job_id: str
    ontobricks_url: str
    ontobricks_domain: str
    ontobricks_version: str
    sql_timeout_seconds: int
    sql_cache_ttl_seconds: int

    @classmethod
    def from_env(cls) -> Settings:
        catalog = os.getenv("QUETZAL_CATALOG", "").strip()
        schema = os.getenv("QUETZAL_SCHEMA", "").strip()
        host = _host(
            os.getenv("DATABRICKS_HOST")
            or os.getenv("APP_HOST")
            or ""
        )
        default_model = f"{catalog}.{schema}.quetzal-telecom-assistant" if catalog and schema else ""
        ai_model = os.getenv("QUETZAL_AI_MODEL", default_model).strip()
        return cls(
            catalog=catalog,
            schema=schema,
            host=host,
            warehouse_id=os.getenv("DATABRICKS_WAREHOUSE_ID", "").strip(),
            workspace_id=os.getenv("DATABRICKS_WORKSPACE_ID", os.getenv("WORKSPACE_ID", "")).strip(),
            dashboard_id=os.getenv("QUETZAL_DASHBOARD_ID", "").strip(),
            ai_model=ai_model,
            ai_url=os.getenv("QUETZAL_AI_URL", f"{host}/ai-gateway/mlflow/v1/responses"),
            genie_ingresos_id=os.getenv("QUETZAL_GENIE_INGRESOS_ID", "").strip(),
            genie_clientes_id=os.getenv("QUETZAL_GENIE_CLIENTES_ID", "").strip(),
            genie_red_id=os.getenv("QUETZAL_GENIE_RED_ID", "").strip(),
            graph_job_id=os.getenv("QUETZAL_GRAPH_JOB_ID", ""),
            ontobricks_url=_optional_url(os.getenv("QUETZAL_ONTOBRICKS_URL", "DISABLED")),
            ontobricks_domain=os.getenv("QUETZAL_ONTOBRICKS_DOMAIN", "quetzal-telecom"),
            ontobricks_version=os.getenv(
                "QUETZAL_ONTOBRICKS_VERSION",
                "0.8.0+c17a730df3bd2df54b4e5714091376ff52936e0d",
            ),
            sql_timeout_seconds=_positive_int("QUETZAL_SQL_TIMEOUT_SECONDS", 60),
            sql_cache_ttl_seconds=_positive_int("QUETZAL_SQL_CACHE_TTL_SECONDS", 30),
        )

    @property
    def dashboard_url(self) -> str:
        if not self.host or not self.dashboard_id or not self.workspace_id:
            return ""
        return f"{self.host}/embed/dashboardsv3/{self.dashboard_id}?o={self.workspace_id}"

    @property
    def genie_spaces(self) -> dict[str, dict[str, str]]:
        return {
            "ingresos": {"id": self.genie_ingresos_id, "name": "Ingresos y Facturación", "icon": "dollar-sign"},
            "clientes": {"id": self.genie_clientes_id, "name": "Inteligencia de Clientes", "icon": "users"},
            "red": {"id": self.genie_red_id, "name": "Operaciones de Red", "icon": "radio-tower"},
        }


settings = Settings.from_env()
