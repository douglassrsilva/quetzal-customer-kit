# Databricks notebook source
# MAGIC %md
# MAGIC # Quetzal · Validación del contrato canónico de datos
# MAGIC
# MAGIC Validación de solo lectura de los adaptadores del modo `customer` o de las fuentes sintéticas.

# COMMAND ----------

import json
import re

dbutils.widgets.text("catalog", "")
dbutils.widgets.text("schema", "")

catalog = dbutils.widgets.get("catalog").strip()
schema = dbutils.widgets.get("schema").strip()
identifier = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
if not identifier.fullmatch(catalog) or not identifier.fullmatch(schema):
    raise ValueError("catalog y schema son obligatorios y deben ser identificadores válidos")

fq = f"`{catalog}`.`{schema}`"
required = {
    "bronze_segmentos": {"segmento_id", "segmento_nombre", "marca_comercial"},
    "bronze_planes": {"plan_id", "nombre", "vertical", "tier", "segmento", "precio_usd", "es_bundle"},
    "bronze_torres_red": {"torre_id", "pais_codigo", "ciudad", "latitud", "longitud", "tecnologia", "capacidad_usuarios"},
    "silver_clientes": {"cliente_id", "nombre_completo", "email", "telefono", "pais_codigo", "segmento_id", "estado", "fecha_alta", "antiguedad_dias", "edad", "credit_score", "nps_ultimo", "acepta_marketing"},
    "silver_suscripciones": {"suscripcion_id", "cliente_id", "plan_id", "estado", "fecha_inicio", "fecha_fin", "precio_mensual_usd", "metodo_pago", "auto_renovacion"},
    "silver_facturas": {"factura_id", "suscripcion_id", "cliente_id", "fecha_emision", "fecha_vencimiento", "fecha_pago", "monto_base_usd", "ajustes_usd", "monto_total_usd", "estado_pago", "dias_atraso"},
    "silver_tickets": {"ticket_id", "cliente_id", "fecha_creacion", "categoria", "motivo", "canal", "pais_codigo", "prioridad", "estado", "tiempo_resolucion_horas", "csat_score", "recontacto"},
    "silver_nps": {"nps_id", "cliente_id", "fecha_encuesta", "score", "categoria_nps", "canal_encuesta", "respondida"},
    "silver_telemetria_red": {"torre_id", "pais_codigo", "ciudad", "tecnologia", "timestamp", "usuarios_conectados", "capacidad_usuarios", "uso_capacidad_pct", "latencia_ms", "packet_loss_pct", "throughput_mbps", "temperatura_equipo_c", "alerta"},
    "silver_cdrs": {"cdr_id", "cliente_id", "suscripcion_id", "plan_id", "pais_codigo", "fecha", "fecha_hora", "tipo_evento", "duracion_seg", "datos_mb", "tecnologia_red", "calidad_señal_dbm", "llamada_caida"},
    "silver_churn_features": {"cliente_id", "pais_codigo", "segmento_id", "estado", "edad", "antiguedad_dias", "credit_score", "nps_ultimo", "total_suscripciones", "suscripciones_activas", "gasto_mensual_total", "total_facturas", "facturas_vencidas", "total_tickets", "tickets_cancelacion", "churn_risk_score", "churned"},
    "gold_churn_predictions": {"cliente_id", "churn_probability", "risk_tier", "scored_at"},
    "gold_clv_segments": {"cliente_id", "revenue_lifetime_est", "segment", "scored_at"},
    "gold_customer_satisfaction": {"mes", "pais_codigo", "nps_index", "avg_csat"},
    "gold_network_health": {"hora", "pais_codigo", "avg_latencia_ms", "avg_uso_capacidad_pct", "uptime_pct"},
    "gold_network_anomalies": {"torre_id", "pais_codigo", "timestamp", "is_anomaly", "anomaly_score", "anomaly_severity"},
    "gold_subscriber_metrics": {"mes", "pais_codigo", "segmento_id", "clientes_activos", "tasa_churn_pct"},
    "gold_billing_health": {"mes", "pais_codigo", "num_facturas", "facturacion_total_usd", "pct_vencida"},
    "gold_revenue_by_country_service": {"mes", "pais_codigo", "vertical", "total_revenue_usd", "unique_customers"},
    "gold_arpu_by_segment": {"mes", "pais_codigo", "segmento_id", "total_revenue_usd", "unique_customers", "arpu_usd"},
}

available = {row.tableName.lower() for row in spark.sql(f"SHOW TABLES IN {fq}").collect()}
report = []
failures = []
for table, columns in required.items():
    if table not in available:
        report.append({"table": table, "status": "MISSING_TABLE"})
        failures.append(f"falta la tabla {table}")
        continue
    actual = {
        row.col_name.lower()
        for row in spark.sql(f"DESCRIBE {fq}.`{table}`").collect()
        if row.col_name and not row.col_name.startswith("#")
    }
    missing = sorted(columns - actual)
    row_count = spark.sql(f"SELECT COUNT(*) AS count FROM {fq}.`{table}`").first()["count"]
    status = "READY" if not missing and row_count > 0 else "INVALID"
    report.append({"table": table, "status": status, "row_count": row_count, "missing_columns": missing})
    if missing:
        failures.append(f"{table}: faltan {', '.join(missing)}")
    if row_count == 0:
        failures.append(f"{table}: está vacía")

result = {
    "catalog": catalog,
    "schema": schema,
    "status": "READY" if not failures else "FAILED",
    "tables": report,
    "failures": failures,
}
print(json.dumps(result, ensure_ascii=False, indent=2))
if failures:
    raise RuntimeError("La validación del contrato canónico falló: " + "; ".join(failures))
