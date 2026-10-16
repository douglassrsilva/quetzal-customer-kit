# Databricks notebook source
# MAGIC %md
# MAGIC # Quetzal · Certificación de datos sintéticos
# MAGIC
# MAGIC Esta tarea es un control de calidad bloqueante. El job finaliza correctamente
# MAGIC solo cuando los datos cumplen el contrato canónico y cubren los flujos
# MAGIC funcionales de telecomunicaciones.

# COMMAND ----------

from __future__ import annotations

import json
import re
from datetime import date
from uuid import uuid4

dbutils.widgets.text("catalog", "")
dbutils.widgets.text("schema", "")
dbutils.widgets.text("customer_count", "10000")
dbutils.widgets.text("seed", "42")
dbutils.widgets.text("anchor_date", "2026-09-29")

catalog = dbutils.widgets.get("catalog").strip()
schema = dbutils.widgets.get("schema").strip()
customer_count = int(dbutils.widgets.get("customer_count"))
seed = int(dbutils.widgets.get("seed"))
anchor_date = dbutils.widgets.get("anchor_date").strip()

identifier = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
if not identifier.fullmatch(catalog) or not identifier.fullmatch(schema):
    raise ValueError("catalog y schema son obligatorios y deben ser identificadores válidos")
if not 1_000 <= customer_count <= 250_000:
    raise ValueError("customer_count debe estar entre 1.000 y 250.000")
date.fromisoformat(anchor_date)

fq = f"`{catalog}`.`{schema}`"
subscription_count = round(customer_count * 1.4)
expected_counts = {
    "bronze_segmentos": 3,
    "bronze_planes": 45,
    "bronze_torres_red": 240,
    "silver_clientes": customer_count,
    "silver_suscripciones": subscription_count,
    "silver_facturas": subscription_count * 12,
    "silver_tickets": round(customer_count * 1.8),
    "silver_nps": round(customer_count * 1.2),
    "silver_telemetria_red": 240 * 72,
    "silver_cdrs": customer_count * 12,
    "silver_churn_features": customer_count,
    "gold_churn_predictions": customer_count,
    "gold_clv_segments": customer_count,
    "gold_network_health": 12 * 72,
    "gold_network_anomalies": 240 * 72,
    "gold_subscriber_metrics": 12 * 12 * 3,
    "gold_billing_health": 12 * 12,
    "gold_revenue_by_country_service": 12 * 12 * 5,
    "gold_arpu_by_segment": 12 * 12 * 3,
}

required_columns = {
    "bronze_segmentos": {"segmento_id", "segmento_nombre", "marca_comercial"},
    "bronze_planes": {"plan_id", "nombre", "vertical", "tier", "segmento", "precio_usd", "data_gb", "internet_mbps", "minutos", "tv_canales", "es_bundle"},
    "bronze_torres_red": {"torre_id", "pais_codigo", "ciudad", "latitud", "longitud", "tecnologia", "capacidad_usuarios"},
    "silver_clientes": {"cliente_id", "nombre", "apellido_1", "apellido_2", "nombre_completo", "email", "telefono", "fecha_nacimiento", "edad", "sexo", "pais_codigo", "segmento_id", "fecha_alta", "antiguedad_dias", "estado", "canal_adquisicion", "credit_score", "nps_ultimo", "acepta_marketing", "_ingested_at", "_rescued_data"},
    "silver_suscripciones": {"suscripcion_id", "cliente_id", "plan_id", "estado", "fecha_inicio", "fecha_fin", "precio_mensual_usd", "metodo_pago", "auto_renovacion"},
    "silver_facturas": {"factura_id", "suscripcion_id", "cliente_id", "fecha_emision", "fecha_vencimiento", "fecha_pago", "monto_base_usd", "ajustes_usd", "monto_total_usd", "estado_pago", "dias_atraso"},
    "silver_tickets": {"ticket_id", "cliente_id", "fecha_creacion", "categoria", "motivo", "canal", "pais_codigo", "prioridad", "estado", "tiempo_resolucion_horas", "csat_score", "recontacto", "_ingested_at", "_rescued_data"},
    "silver_nps": {"nps_id", "cliente_id", "fecha_encuesta", "score", "categoria_nps", "canal_encuesta", "respondida", "_ingested_at", "_rescued_data"},
    "silver_telemetria_red": {"torre_id", "pais_codigo", "ciudad", "tecnologia", "timestamp", "usuarios_conectados", "capacidad_usuarios", "uso_capacidad_pct", "latencia_ms", "packet_loss_pct", "throughput_mbps", "temperatura_equipo_c", "alerta", "_ingested_at", "_rescued_data"},
    "silver_cdrs": {"cdr_id", "cliente_id", "suscripcion_id", "plan_id", "pais_codigo", "fecha", "fecha_hora", "tipo_evento", "duracion_seg", "datos_mb", "tecnologia_red", "calidad_señal_dbm", "llamada_caida", "_ingested_at", "_rescued_data"},
    "silver_churn_features": {"cliente_id", "pais_codigo", "segmento_id", "estado", "edad", "antiguedad_dias", "credit_score", "nps_ultimo", "canal_adquisicion", "total_suscripciones", "suscripciones_activas", "gasto_mensual_total", "total_facturas", "facturas_vencidas", "avg_monto_factura", "avg_dias_atraso", "max_dias_atraso", "total_tickets", "tickets_cancelacion", "total_recontactos", "avg_csat", "churn_risk_score", "churned", "_ingested_at", "_rescued_data"},
    "gold_churn_predictions": {"cliente_id", "pais_codigo", "segmento_id", "gasto_mensual_total", "churn_probability", "churn_predicted", "risk_tier", "scored_at"},
    "gold_churn_risk_summary": {"pais_codigo", "segmento_id", "riesgo_bucket", "num_clientes", "avg_risk_score", "avg_gasto_mensual", "avg_tickets", "avg_dias_atraso", "ya_churned"},
    "gold_clv_segments": {"cliente_id", "pais_codigo", "segmento_id", "gasto_mensual_total", "revenue_lifetime_est", "churn_risk_score", "segment", "segment_name", "scored_at"},
    "gold_customer_satisfaction": {"mes", "pais_codigo", "total_encuestas", "promotores", "detractores", "nps_index", "total_evaluaciones_csat", "avg_csat", "csat_top2_pct", "avg_nps_score"},
    "gold_network_health": {"hora", "pais_codigo", "total_mediciones", "avg_latencia_ms", "avg_packet_loss_pct", "avg_throughput_mbps", "avg_uso_capacidad_pct", "torres_en_alerta", "uptime_pct"},
    "gold_network_anomalies": {"torre_id", "pais_codigo", "ciudad", "tecnologia", "timestamp", "uso_capacidad_pct", "latencia_ms", "packet_loss_pct", "throughput_mbps", "alerta", "is_anomaly", "anomaly_score", "anomaly_severity", "scored_at"},
    "gold_subscriber_metrics": {"mes", "pais_codigo", "segmento_id", "clientes_activos", "suscripciones_activas", "suscripciones_nuevas", "suscripciones_canceladas", "tasa_churn_pct"},
    "gold_billing_health": {"mes", "pais_codigo", "num_facturas", "facturacion_total_usd", "monto_pagado_usd", "monto_vencido_usd", "pct_pagada", "pct_vencida", "tasa_cobro_pct", "avg_dias_atraso", "cartera_vencida_usd"},
    "gold_revenue_by_country_service": {"mes", "pais_codigo", "vertical", "total_revenue_usd", "ingresos_totales_usd", "ingresos_cobrados_usd", "num_facturas", "unique_customers"},
    "gold_arpu_by_segment": {"mes", "pais_codigo", "segmento_id", "total_revenue_usd", "unique_customers", "clientes_unicos", "arpu_usd"},
}


def sql(statement: str):
    return spark.sql(statement)


def scalar(statement: str, column: str = "n"):
    row = sql(statement).first()
    return row[column]


def table_property(table: str, key: str) -> str | None:
    try:
        row = sql(f"SHOW TBLPROPERTIES {fq}.`{table}` ('{key}')").first()
        value = row["value"] if row is not None else None
        return None if value is None or "does not have property" in value else value
    except Exception:
        return None


failures: list[str] = []
checks: list[dict[str, object]] = []
available = {row.tableName.lower() for row in sql(f"SHOW TABLES IN {fq}").collect()}
generation_run_ids: set[str] = set()

for table, columns in required_columns.items():
    if table not in available:
        failures.append(f"falta la tabla {table}")
        checks.append({"check": f"schema:{table}", "status": "FAIL", "detail": "falta la tabla"})
        continue
    actual_columns = {
        row.col_name.lower()
        for row in sql(f"DESCRIBE {fq}.`{table}`").collect()
        if row.col_name and not row.col_name.startswith("#")
    }
    missing = sorted(columns - actual_columns)
    if missing:
        failures.append(f"{table}: faltan las columnas {', '.join(missing)}")
    checks.append({"check": f"schema:{table}", "status": "PASS" if not missing else "FAIL", "detail": missing})

    properties = {
        "data_classification": table_property(table, "data_classification"),
        "generated_by": table_property(table, "generated_by"),
        "generation_seed": table_property(table, "generation_seed"),
        "generation_anchor_date": table_property(table, "generation_anchor_date"),
        "generation_customer_count": table_property(table, "generation_customer_count"),
        "generation_run_id": table_property(table, "generation_run_id"),
    }
    expected_properties = {
        "data_classification": "synthetic",
        "generated_by": "quetzal-customer-kit",
        "generation_seed": str(seed),
        "generation_anchor_date": anchor_date,
        "generation_customer_count": str(customer_count),
    }
    mismatches = [f"{key}={properties[key]!r}" for key, value in expected_properties.items() if properties[key] != value]
    if properties["generation_run_id"]:
        generation_run_ids.add(str(properties["generation_run_id"]))
    if mismatches:
        failures.append(f"{table}: propiedades de procedencia inválidas ({', '.join(mismatches)})")
    checks.append({"check": f"provenance:{table}", "status": "PASS" if not mismatches else "FAIL", "detail": mismatches})

for table, expected in expected_counts.items():
    if table not in available:
        continue
    actual = scalar(f"SELECT count(*) AS n FROM {fq}.`{table}`")
    passed = actual == expected
    if not passed:
        failures.append(f"{table}: se esperaban {expected} filas y se encontraron {actual}")
    checks.append({"check": f"volume:{table}", "status": "PASS" if passed else "FAIL", "actual": actual, "expected": expected})

if len(generation_run_ids) != 1:
    failures.append(f"las tablas no comparten un único generation_run_id: {sorted(generation_run_ids)}")


def zero_check(name: str, query: str) -> None:
    actual = int(scalar(query))
    if actual != 0:
        failures.append(f"{name}: se esperaban 0 incumplimientos y se encontraron {actual}")
    checks.append({"check": name, "status": "PASS" if actual == 0 else "FAIL", "violations": actual})


def minimum_check(name: str, query: str, minimum: int) -> None:
    actual = int(scalar(query))
    if actual < minimum:
        failures.append(f"{name}: se esperaban al menos {minimum} filas y se encontraron {actual}")
    checks.append({"check": name, "status": "PASS" if actual >= minimum else "FAIL", "actual": actual, "minimum": minimum})


# Claves primarias y relaciones.
for table, key in {
    "bronze_segmentos": "segmento_id",
    "bronze_planes": "plan_id",
    "bronze_torres_red": "torre_id",
    "silver_clientes": "cliente_id",
    "silver_suscripciones": "suscripcion_id",
    "silver_facturas": "factura_id",
    "silver_tickets": "ticket_id",
    "silver_nps": "nps_id",
    "silver_cdrs": "cdr_id",
}.items():
    zero_check(
        f"primary_key:{table}",
        f"SELECT count(*) AS n FROM (SELECT `{key}` FROM {fq}.`{table}` GROUP BY `{key}` HAVING `{key}` IS NULL OR count(*) > 1)",
    )

zero_check("fk:subscriptions_customers", f"SELECT count(*) AS n FROM {fq}.silver_suscripciones s LEFT ANTI JOIN {fq}.silver_clientes c ON s.cliente_id=c.cliente_id")
zero_check("fk:subscriptions_plans", f"SELECT count(*) AS n FROM {fq}.silver_suscripciones s LEFT ANTI JOIN {fq}.bronze_planes p ON s.plan_id=p.plan_id")
zero_check("fk:invoices_subscriptions", f"SELECT count(*) AS n FROM {fq}.silver_facturas f LEFT ANTI JOIN {fq}.silver_suscripciones s ON f.suscripcion_id=s.suscripcion_id AND f.cliente_id=s.cliente_id")
zero_check("fk:tickets_customers", f"SELECT count(*) AS n FROM {fq}.silver_tickets t LEFT ANTI JOIN {fq}.silver_clientes c ON t.cliente_id=c.cliente_id")
zero_check("fk:nps_customers", f"SELECT count(*) AS n FROM {fq}.silver_nps n LEFT ANTI JOIN {fq}.silver_clientes c ON n.cliente_id=c.cliente_id")
zero_check("fk:telemetry_towers", f"SELECT count(*) AS n FROM {fq}.silver_telemetria_red m LEFT ANTI JOIN {fq}.bronze_torres_red t ON m.torre_id=t.torre_id")
zero_check("fk:cdr_customer_subscription", f"SELECT count(*) AS n FROM {fq}.silver_cdrs d LEFT ANTI JOIN {fq}.silver_suscripciones s ON d.suscripcion_id=s.suscripcion_id AND d.cliente_id=s.cliente_id AND d.plan_id=s.plan_id")

# Reglas de dominio, contabilidad y privacidad.
zero_check("pii:fictitious_only", f"""SELECT count(*) AS n FROM {fq}.silver_clientes
  WHERE nombre_completo NOT LIKE 'Cliente Demo %' OR email NOT LIKE 'customer%@example.com' OR telefono NOT LIKE '+000%'""")
zero_check("domain:countries", f"""SELECT count(*) AS n FROM {fq}.silver_clientes
  WHERE pais_codigo NOT IN ('PA','MX','CO','BR','AR','CL','PE','EC','CR','GT','DO','UY')""")
zero_check("domain:segments", f"SELECT count(*) AS n FROM {fq}.silver_clientes WHERE segmento_id NOT IN ('PER','COM','ENT')")
zero_check("business:subscription_dates", f"SELECT count(*) AS n FROM {fq}.silver_suscripciones WHERE fecha_fin IS NOT NULL AND fecha_fin < fecha_inicio")
zero_check("business:invoice_equation", f"SELECT count(*) AS n FROM {fq}.silver_facturas WHERE abs(monto_total_usd - (monto_base_usd + ajustes_usd)) > 0.011 OR dias_atraso < 0")
zero_check("business:nps_consistency", f"""SELECT count(*) AS n FROM {fq}.silver_nps
  WHERE (respondida AND (score IS NULL OR categoria_nps IS NULL))
     OR (NOT respondida AND (score IS NOT NULL OR categoria_nps IS NOT NULL))
     OR (score IS NOT NULL AND (score < 0 OR score > 10))
     OR (score <= 6 AND categoria_nps <> 'DETRACTOR')
     OR (score BETWEEN 7 AND 8 AND categoria_nps <> 'PASSIVE')
     OR (score >= 9 AND categoria_nps <> 'PROMOTER')""")
zero_check("business:telemetry_bounds", f"""SELECT count(*) AS n FROM {fq}.silver_telemetria_red
  WHERE usuarios_conectados < 0 OR usuarios_conectados > capacidad_usuarios
     OR uso_capacidad_pct < 0 OR uso_capacidad_pct > 100
     OR packet_loss_pct < 0 OR throughput_mbps < 0""")
zero_check("business:churn_bounds", f"SELECT count(*) AS n FROM {fq}.gold_churn_predictions WHERE churn_probability < 0 OR churn_probability > 1")
zero_check("business:single_churn_source", f"""SELECT count(*) AS n FROM {fq}.gold_churn_predictions p
  JOIN {fq}.silver_churn_features f USING (cliente_id)
  WHERE abs(p.churn_probability - f.churn_risk_score) > 0.00001""")

# Controles de cobertura para los flujos funcionales.
minimum_check("coverage:all_countries", f"SELECT count(DISTINCT pais_codigo) AS n FROM {fq}.silver_clientes", 12)
minimum_check("coverage:all_segments", f"SELECT count(DISTINCT segmento_id) AS n FROM {fq}.silver_clientes", 3)
minimum_check("coverage:all_product_verticals", f"SELECT count(DISTINCT vertical) AS n FROM {fq}.bronze_planes", 5)
minimum_check("journey:customer_360", f"""SELECT count(*) AS n FROM {fq}.silver_clientes c
  JOIN {fq}.silver_suscripciones s USING (cliente_id)
  JOIN {fq}.silver_facturas f USING (cliente_id, suscripcion_id)
  JOIN {fq}.silver_tickets t USING (cliente_id)
  JOIN {fq}.silver_nps n USING (cliente_id)""", customer_count)
minimum_check("journey:proactive_retention", f"SELECT count(*) AS n FROM {fq}.gold_churn_predictions WHERE churn_probability >= 0.65", max(5, customer_count // 2000))
minimum_check("journey:campaign_eligible", f"""SELECT count(*) AS n FROM {fq}.gold_churn_predictions p
  JOIN {fq}.silver_clientes c USING (cliente_id)
  WHERE p.churn_probability >= 0.40 AND c.acepta_marketing AND c.estado='ACTIVO'""", max(50, customer_count // 100))
minimum_check("journey:voice_of_customer", f"SELECT count(*) AS n FROM {fq}.silver_tickets WHERE categoria IN ('RED','COBRANZA','CANCELACION','PRODUCTO')", customer_count)
minimum_check("journey:sla_breach_candidates", f"SELECT count(*) AS n FROM {fq}.silver_tickets WHERE tiempo_resolucion_horas > 24", max(100, customer_count // 20))
minimum_check("journey:billing_delinquency", f"SELECT count(*) AS n FROM {fq}.silver_facturas WHERE estado_pago='vencida'", max(100, customer_count // 10))
minimum_check("journey:network_incidents", f"""SELECT count(*) AS n FROM {fq}.gold_network_anomalies
  WHERE is_anomaly AND timestamp >= TIMESTAMP('{anchor_date} 23:00:00') - INTERVAL 24 HOURS""", 5)
minimum_check("journey:next_best_offer", f"""SELECT count(*) AS n FROM {fq}.silver_clientes c
  WHERE c.estado='ACTIVO' AND c.acepta_marketing
    AND EXISTS (SELECT 1 FROM {fq}.bronze_planes p WHERE p.segmento=c.segmento_id)""", max(100, customer_count // 10))

# Un fingerprint compacto y estable detecta variaciones entre ejecuciones equivalentes.
fingerprint = scalar(f"""
  SELECT sha2(concat_ws('|',
    cast((SELECT sum(pmod(xxhash64(cliente_id,nombre_completo,email,pais_codigo,segmento_id,estado),1000000007)) FROM {fq}.silver_clientes) AS STRING),
    cast((SELECT sum(pmod(xxhash64(suscripcion_id,cliente_id,plan_id,estado,precio_mensual_usd),1000000007)) FROM {fq}.silver_suscripciones) AS STRING),
    cast((SELECT sum(pmod(xxhash64(factura_id,cliente_id,monto_total_usd,estado_pago,dias_atraso),1000000007)) FROM {fq}.silver_facturas) AS STRING),
    cast((SELECT sum(pmod(xxhash64(torre_id,timestamp,latencia_ms,alerta),1000000007)) FROM {fq}.silver_telemetria_red) AS STRING),
    cast((SELECT sum(pmod(xxhash64(cliente_id,churn_probability,risk_tier),1000000007)) FROM {fq}.gold_churn_predictions) AS STRING)
  ), 256) AS fingerprint
""", "fingerprint")

certification_table = "ops_synthetic_certifications"
if spark.catalog.tableExists(f"{catalog}.{schema}.{certification_table}"):
    if table_property(certification_table, "data_classification") != "synthetic" or table_property(certification_table, "generated_by") != "quetzal-customer-kit":
        failures.append("ops_synthetic_certifications existe pero no pertenece a este generador sintético")
else:
    sql(f"""
    CREATE TABLE {fq}.{certification_table} (
      certification_id STRING NOT NULL,
      generation_run_id STRING NOT NULL,
      certified_at TIMESTAMP NOT NULL,
      customer_count BIGINT NOT NULL,
      seed INT NOT NULL,
      anchor_date DATE NOT NULL,
      dataset_fingerprint STRING NOT NULL,
      check_count INT NOT NULL,
      status STRING NOT NULL
    ) USING DELTA
    TBLPROPERTIES ('data_classification'='synthetic','generated_by'='quetzal-customer-kit')
    """)

if spark.catalog.tableExists(f"{catalog}.{schema}.{certification_table}"):
    conflicting = int(scalar(f"""SELECT count(*) AS n FROM {fq}.{certification_table}
      WHERE customer_count={customer_count} AND seed={seed} AND anchor_date=DATE('{anchor_date}')
        AND status='CERTIFIED' AND dataset_fingerprint <> '{fingerprint}'"""))
    if conflicting:
        failures.append("falló el control de determinismo: las mismas entradas produjeron otro fingerprint")

status = "CERTIFIED" if not failures else "FAILED"
generation_run_id = next(iter(generation_run_ids), "UNKNOWN")
report = {
    "status": status,
    "catalog": catalog,
    "schema": schema,
    "generation_run_id": generation_run_id,
    "customer_count": customer_count,
    "seed": seed,
    "anchor_date": anchor_date,
    "dataset_fingerprint": fingerprint,
    "checks_passed": sum(item["status"] == "PASS" for item in checks),
    "checks_total": len(checks),
    "failures": failures,
    "checks": checks,
}
print(json.dumps(report, ensure_ascii=False, indent=2))

if failures:
    raise RuntimeError("La certificación de datos sintéticos falló: " + "; ".join(failures))

certification_id = uuid4().hex
sql(f"""
INSERT INTO {fq}.{certification_table}
VALUES ('{certification_id}', '{generation_run_id}', current_timestamp(), {customer_count}, {seed},
        DATE('{anchor_date}'), '{fingerprint}', {len(checks)}, 'CERTIFIED')
""")
dbutils.jobs.taskValues.set(key="certification_id", value=certification_id)
dbutils.jobs.taskValues.set(key="dataset_fingerprint", value=fingerprint)
