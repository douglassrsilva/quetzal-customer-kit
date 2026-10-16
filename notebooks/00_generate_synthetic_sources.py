# Databricks notebook source
# MAGIC %md
# MAGIC # Quetzal · Datos sintéticos deterministas de telecomunicaciones
# MAGIC
# MAGIC Plan de generación: notebook serverless Tier 3, semilla 42, 10.000 clientes,
# MAGIC 11 tablas fuente canónicas y 10 derivaciones Gold. La salida se limita al
# MAGIC catálogo y esquema configurados. Todas las identidades son ficticias y los
# MAGIC datos de contacto no son enrutables.

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
dbutils.widgets.text("overwrite_confirmation", "")

catalog = dbutils.widgets.get("catalog").strip()
schema = dbutils.widgets.get("schema").strip()
customer_count = int(dbutils.widgets.get("customer_count"))
seed = int(dbutils.widgets.get("seed"))
anchor_date = dbutils.widgets.get("anchor_date").strip()
overwrite_confirmation = dbutils.widgets.get("overwrite_confirmation").strip()

identifier = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
if not identifier.fullmatch(catalog) or not identifier.fullmatch(schema):
    raise ValueError("catalog y schema son obligatorios y deben ser identificadores válidos")
if not 1_000 <= customer_count <= 250_000:
    raise ValueError("customer_count debe estar entre 1.000 y 250.000")
if not -(2**31) <= seed < 2**31:
    raise ValueError("seed debe ser un entero de 32 bits con signo")
try:
    date.fromisoformat(anchor_date)
except ValueError as exc:
    raise ValueError("anchor_date debe utilizar el formato ISO YYYY-MM-DD") from exc
if overwrite_confirmation != "SYNTHETIC_DEMO_ONLY":
    raise ValueError("overwrite_confirmation debe ser SYNTHETIC_DEMO_ONLY")

fq = f"`{catalog}`.`{schema}`"
run_id = uuid4().hex
subscription_count = round(customer_count * 1.4)
invoice_count = subscription_count * 12
ticket_count = round(customer_count * 1.8)
nps_count = round(customer_count * 1.2)
cdr_count = customer_count * 12
tower_count = 240
telemetry_count = tower_count * 72

source_counts = {
    "bronze_segmentos": 3,
    "bronze_planes": 45,
    "bronze_torres_red": tower_count,
    "silver_clientes": customer_count,
    "silver_suscripciones": subscription_count,
    "silver_facturas": invoice_count,
    "silver_tickets": ticket_count,
    "silver_nps": nps_count,
    "silver_telemetria_red": telemetry_count,
    "silver_cdrs": cdr_count,
    "silver_churn_features": customer_count,
}
gold_tables = {
    "gold_churn_predictions",
    "gold_churn_risk_summary",
    "gold_clv_segments",
    "gold_customer_satisfaction",
    "gold_network_health",
    "gold_network_anomalies",
    "gold_subscriber_metrics",
    "gold_billing_health",
    "gold_revenue_by_country_service",
    "gold_arpu_by_segment",
}
managed_tables = set(source_counts) | gold_tables


def sql(statement: str):
    return spark.sql(statement)


def table_property(table: str, key: str) -> str | None:
    try:
        row = sql(f"SHOW TBLPROPERTIES {fq}.`{table}` ('{key}')").first()
        value = row["value"] if row is not None else None
        return None if value is None or "does not have property" in value else value
    except Exception:
        return None


# Valida los límites de escritura antes de crear el esquema o reemplazar una tabla.
# Una nueva ejecución solo puede reemplazar tablas creadas por este kit en modo sintético.
for table in sorted(managed_tables):
    if spark.catalog.tableExists(f"{catalog}.{schema}.{table}"):
        classification = table_property(table, "data_classification")
        generator = table_property(table, "generated_by")
        if classification != "synthetic" or generator != "quetzal-customer-kit":
            raise RuntimeError(
                f"No se reemplazará {catalog}.{schema}.{table}: el objeto existente no pertenece "
                "al generador de datos sintéticos de Quetzal"
            )

sql(f"CREATE SCHEMA IF NOT EXISTS {fq}")
sql(f"USE CATALOG `{catalog}`")
sql(f"USE SCHEMA `{schema}`")

generation_report: list[dict[str, object]] = []


def write_table(table: str, select_sql: str, expected_count: int | None = None) -> None:
    sql(f"""
    CREATE OR REPLACE TABLE {fq}.`{table}`
    USING DELTA
    TBLPROPERTIES (
      'data_classification' = 'synthetic',
      'generated_by' = 'quetzal-customer-kit',
      'generation_seed' = '{seed}',
      'generation_anchor_date' = '{anchor_date}',
      'generation_customer_count' = '{customer_count}',
      'generation_run_id' = '{run_id}'
    ) AS
    {select_sql}
    """)
    actual_count = sql(f"SELECT count(*) AS n FROM {fq}.`{table}`").first()["n"]
    if expected_count is not None and actual_count != expected_count:
        raise RuntimeError(f"{table}: se esperaban {expected_count} filas y se generaron {actual_count}")
    generation_report.append({"table": table, "rows": actual_count})


# COMMAND ----------

write_table(
    "bronze_segmentos",
    """
    SELECT * FROM VALUES
      ('PER', 'Personal', 'Quetzal Libre'),
      ('COM', 'Comercial', 'Quetzal Negocios'),
      ('ENT', 'Empresarial', 'Quetzal Enterprise')
    AS segmentos(segmento_id, segmento_nombre, marca_comercial)
    """,
    3,
)

write_table(
    "bronze_planes",
    f"""
    WITH base AS (
      SELECT id,
             element_at(array('PER','COM','ENT'), cast(floor(id / 15) AS INT) + 1) AS segmento,
             element_at(array('Móvil','Internet','TV','Fija','Bundles'), cast(pmod(id, 5) AS INT) + 1) AS vertical,
             element_at(array('Essential','Plus','Max'), cast(pmod(floor(id / 5), 3) AS INT) + 1) AS tier
      FROM range(45)
    )
    SELECT concat('PLN-', segmento, '-', lpad(cast(pmod(id, 15) + 1 AS STRING), 3, '0')) AS plan_id,
           concat('Quetzal ', vertical, ' ', tier) AS nombre,
           vertical, tier, segmento,
           round(
             CASE segmento WHEN 'PER' THEN 18D WHEN 'COM' THEN 42D ELSE 95D END
             + CASE tier WHEN 'Essential' THEN 0D WHEN 'Plus' THEN 18D ELSE 42D END
             + CASE vertical WHEN 'Bundles' THEN 28D WHEN 'Internet' THEN 16D WHEN 'TV' THEN 10D ELSE 4D END,
             2
           ) AS precio_usd,
           CASE WHEN vertical IN ('Móvil','Bundles') THEN
             CASE tier WHEN 'Essential' THEN 12D WHEN 'Plus' THEN 40D ELSE 120D END END AS data_gb,
           CASE WHEN vertical IN ('Internet','Bundles') THEN
             CASE tier WHEN 'Essential' THEN 100 WHEN 'Plus' THEN 400 ELSE 1000 END END AS internet_mbps,
           CASE WHEN vertical IN ('Móvil','Fija','Bundles') THEN
             CASE tier WHEN 'Essential' THEN 500 WHEN 'Plus' THEN 2000 ELSE 10000 END END AS minutos,
           CASE WHEN vertical IN ('TV','Bundles') THEN
             CASE tier WHEN 'Essential' THEN 70 WHEN 'Plus' THEN 140 ELSE 220 END END AS tv_canales,
           vertical = 'Bundles' AS es_bundle
    FROM base
    """,
    45,
)

write_table(
    "bronze_torres_red",
    f"""
    WITH base AS (
      SELECT id,
             cast(pmod(id, 12) AS INT) AS country_idx,
             xxhash64(id, {seed}) AS h
      FROM range({tower_count})
    )
    SELECT concat('TWR-DEMO-', lpad(cast(id + 1 AS STRING), 5, '0')) AS torre_id,
           element_at(array('PA','MX','CO','BR','AR','CL','PE','EC','CR','GT','DO','UY'), country_idx + 1) AS pais_codigo,
           element_at(array('Ciudad de Panamá','Ciudad de México','Bogotá','São Paulo','Buenos Aires','Santiago','Lima','Quito','San José','Ciudad de Guatemala','Santo Domingo','Montevideo'), country_idx + 1) AS ciudad,
           round(element_at(array(8.98D,19.43D,4.71D,-23.55D,-34.60D,-33.45D,-12.05D,-0.18D,9.93D,14.63D,18.49D,-34.90D), country_idx + 1)
                 + (pmod(h, 2001) - 1000) / 10000D, 5) AS latitud,
           round(element_at(array(-79.52D,-99.13D,-74.07D,-46.63D,-58.38D,-70.67D,-77.04D,-78.47D,-84.08D,-90.51D,-69.93D,-56.16D), country_idx + 1)
                 + (pmod(h, 1703) - 851) / 10000D, 5) AS longitud,
           CASE WHEN pmod(h, 10) < 3 THEN '5G' WHEN pmod(h, 10) = 9 THEN 'Fiber' ELSE '4G' END AS tecnologia,
           cast(700 + pmod(h, 4301) AS INT) AS capacidad_usuarios
    FROM base
    """,
    tower_count,
)

# COMMAND ----------

write_table(
    "silver_clientes",
    f"""
    WITH base AS (
      SELECT id,
             xxhash64(id, {seed}) AS h0,
             xxhash64(id, {seed + 1}) AS h1,
             xxhash64(id, {seed + 2}) AS h2,
             xxhash64(id, {seed + 3}) AS h3
      FROM range({customer_count})
    ), shaped AS (
      SELECT *,
             18 + pmod(h0, 68) AS generated_age,
             CASE WHEN pmod(h1, 100) < 70 THEN 'PER'
                  WHEN pmod(h1, 100) < 92 THEN 'COM' ELSE 'ENT' END AS generated_segment,
             element_at(array('PA','MX','CO','BR','AR','CL','PE','EC','CR','GT','DO','UY'), cast(pmod(h2, 12) AS INT) + 1) AS generated_country
      FROM base
    )
    SELECT concat('CUS-DEMO-', lpad(cast(id + 1 AS STRING), 6, '0')) AS cliente_id,
           'Cliente' AS nombre,
           'Demo' AS apellido_1,
           lpad(cast(id + 1 AS STRING), 6, '0') AS apellido_2,
           concat('Cliente Demo ', lpad(cast(id + 1 AS STRING), 6, '0')) AS nombre_completo,
           concat('customer', lpad(cast(id + 1 AS STRING), 6, '0'), '@example.com') AS email,
           concat('+000', lpad(cast(id + 1 AS STRING), 12, '0')) AS telefono,
           date_sub(DATE('{anchor_date}'), cast(generated_age * 365 + pmod(h3, 365) AS INT)) AS fecha_nacimiento,
           cast(generated_age AS INT) AS edad,
           element_at(array('F','M','X'), cast(pmod(h0, 3) AS INT) + 1) AS sexo,
           generated_country AS pais_codigo,
           generated_segment AS segmento_id,
           date_sub(DATE('{anchor_date}'), cast(30 + pmod(h1, 2891) AS INT)) AS fecha_alta,
           cast(30 + pmod(h1, 2891) AS INT) AS antiguedad_dias,
           CASE WHEN pmod(h2, 100) < 92 THEN 'ACTIVO'
                WHEN pmod(h2, 100) < 96 THEN 'SUSPENDIDO' ELSE 'CANCELADO' END AS estado,
           element_at(array('DIGITAL','TIENDA','PARTNER','CALL_CENTER'), cast(pmod(h3, 4) AS INT) + 1) AS canal_adquisicion,
           cast(300 + pmod(h0, 551) AS INT) AS credit_score,
           cast(pmod(xxhash64(id, {seed + 4}), 11) AS INT) AS nps_ultimo,
           pmod(h3, 100) < 72 AS acepta_marketing,
           TIMESTAMP('{anchor_date} 23:59:00') AS _ingested_at,
           cast(NULL AS STRING) AS _rescued_data
    FROM shaped
    """,
    customer_count,
)

write_table(
    "silver_suscripciones",
    f"""
    WITH generated AS (
      SELECT id,
             pmod(id, {customer_count}) AS customer_idx,
             xxhash64(id, {seed + 10}) AS h0,
             xxhash64(id, {seed + 11}) AS h1
      FROM range({subscription_count})
    ), joined AS (
      SELECT g.*, c.cliente_id, c.segmento_id, c.estado AS customer_status,
             concat('PLN-', c.segmento_id, '-', lpad(cast(pmod(g.h0, 15) + 1 AS STRING), 3, '0')) AS selected_plan,
             CASE WHEN c.estado = 'CANCELADO' THEN 'CANCELADA'
                  WHEN pmod(g.h1, 100) < 84 THEN 'ACTIVA'
                  WHEN pmod(g.h1, 100) < 93 THEN 'SUSPENDIDA' ELSE 'CANCELADA' END AS subscription_status,
             date_sub(DATE('{anchor_date}'), cast(30 + pmod(g.h0, 2101) AS INT)) AS start_date
      FROM generated g
      JOIN {fq}.silver_clientes c
        ON c.cliente_id = concat('CUS-DEMO-', lpad(cast(g.customer_idx + 1 AS STRING), 6, '0'))
    )
    SELECT concat('SUB-DEMO-', lpad(cast(j.id + 1 AS STRING), 8, '0')) AS suscripcion_id,
           j.cliente_id,
           j.selected_plan AS plan_id,
           j.subscription_status AS estado,
           j.start_date AS fecha_inicio,
           CASE WHEN j.subscription_status = 'CANCELADA'
                THEN greatest(j.start_date, date_sub(DATE('{anchor_date}'), cast(pmod(j.h1, 366) AS INT))) END AS fecha_fin,
           round(p.precio_usd * (1D - pmod(j.h0, 16) / 100D), 2) AS precio_mensual_usd,
           element_at(array('CARD','DEBIT','INVOICE','CASH'), cast(pmod(j.h1, 4) AS INT) + 1) AS metodo_pago,
           CASE WHEN pmod(j.h1, 4) IN (0,1) THEN pmod(j.h0, 100) < 88 ELSE pmod(j.h0, 100) < 48 END AS auto_renovacion
    FROM joined j
    JOIN {fq}.bronze_planes p ON p.plan_id = j.selected_plan
    """,
    subscription_count,
)

write_table(
    "silver_facturas",
    f"""
    WITH generated AS (
      SELECT id,
             cast(floor(id / 12) AS BIGINT) AS subscription_idx,
             cast(pmod(id, 12) AS INT) AS month_offset,
             xxhash64(id, {seed + 20}) AS h0,
             xxhash64(id, {seed + 21}) AS h1
      FROM range({invoice_count})
    ), base AS (
      SELECT g.*, s.suscripcion_id, s.cliente_id, s.precio_mensual_usd,
             add_months(trunc(DATE('{anchor_date}'), 'MM'), -g.month_offset) AS issue_date,
             CASE WHEN g.month_offset = 0 AND pmod(g.h0, 100) BETWEEN 88 AND 91 THEN 'pendiente'
                  WHEN pmod(g.h0, 100) >= 92 THEN 'vencida' ELSE 'pagada' END AS payment_status,
             round((pmod(g.h1, 1501) - 500) / 100D, 2) AS adjustment
      FROM generated g
      JOIN {fq}.silver_suscripciones s
        ON s.suscripcion_id = concat('SUB-DEMO-', lpad(cast(g.subscription_idx + 1 AS STRING), 8, '0'))
    ), dated AS (
      SELECT *, date_add(issue_date, 10) AS due_date,
             round(precio_mensual_usd + adjustment, 2) AS total_amount
      FROM base
    )
    SELECT concat('INV-DEMO-', lpad(cast(id + 1 AS STRING), 10, '0')) AS factura_id,
           suscripcion_id, cliente_id,
           issue_date AS fecha_emision,
           due_date AS fecha_vencimiento,
           CASE WHEN payment_status = 'pagada'
                THEN date_add(due_date, cast(pmod(h1, 9) - 3 AS INT)) END AS fecha_pago,
           precio_mensual_usd AS monto_base_usd,
           adjustment AS ajustes_usd,
           total_amount AS monto_total_usd,
           payment_status AS estado_pago,
           CASE WHEN payment_status = 'vencida' THEN cast(5 + pmod(h1, 41) AS INT)
                WHEN payment_status = 'pagada' THEN cast(greatest(0, pmod(h1, 9) - 3) AS INT)
                ELSE 0 END AS dias_atraso
    FROM dated
    """,
    invoice_count,
)

write_table(
    "silver_tickets",
    f"""
    WITH generated AS (
      SELECT id, pmod(id, {customer_count}) AS customer_idx,
             xxhash64(id, {seed + 30}) AS h0,
             xxhash64(id, {seed + 31}) AS h1,
             xxhash64(id, {seed + 32}) AS h2
      FROM range({ticket_count})
    ), joined AS (
      SELECT g.*, c.cliente_id, c.pais_codigo,
             CASE WHEN pmod(g.h0, 100) < 45 THEN 'RED'
                  WHEN pmod(g.h0, 100) < 70 THEN 'COBRANZA'
                  WHEN pmod(g.h0, 100) < 85 THEN 'CANCELACION' ELSE 'PRODUCTO' END AS category,
             CASE WHEN pmod(g.h1, 100) < 12 THEN 'ABIERTO'
                  WHEN pmod(g.h1, 100) < 22 THEN 'EN_PROGRESO'
                  WHEN pmod(g.h1, 100) < 72 THEN 'RESUELTO' ELSE 'CERRADO' END AS ticket_status
      FROM generated g
      JOIN {fq}.silver_clientes c
        ON c.cliente_id = concat('CUS-DEMO-', lpad(cast(g.customer_idx + 1 AS STRING), 6, '0'))
    )
    SELECT concat('TKT-DEMO-', lpad(cast(id + 1 AS STRING), 8, '0')) AS ticket_id,
           cliente_id,
           timestampadd(HOUR, -cast(pmod(h0, 4320) AS INT), TIMESTAMP('{anchor_date} 23:00:00')) AS fecha_creacion,
           category AS categoria,
           CASE category WHEN 'RED' THEN element_at(array('Cobertura intermitente','Latencia alta','Llamada caída'), cast(pmod(h1, 3) AS INT) + 1)
                         WHEN 'COBRANZA' THEN element_at(array('Cargo no reconocido','Factura vencida','Ajuste pendiente'), cast(pmod(h1, 3) AS INT) + 1)
                         WHEN 'CANCELACION' THEN element_at(array('Precio','Calidad del servicio','Cambio de proveedor'), cast(pmod(h1, 3) AS INT) + 1)
                         ELSE element_at(array('Cambio de plan','Activación','Compatibilidad'), cast(pmod(h1, 3) AS INT) + 1) END AS motivo,
           element_at(array('APP','CALL','CHAT','STORE'), cast(pmod(h2, 4) AS INT) + 1) AS canal,
           pais_codigo,
           CASE WHEN pmod(h2, 100) < 7 THEN 'CRITICAL' WHEN pmod(h2, 100) < 25 THEN 'HIGH'
                WHEN pmod(h2, 100) < 70 THEN 'MEDIUM' ELSE 'LOW' END AS prioridad,
           ticket_status AS estado,
           CASE WHEN ticket_status IN ('RESUELTO','CERRADO') THEN round(2D + pmod(h1, 143) / 1.7D, 2) END AS tiempo_resolucion_horas,
           CASE WHEN ticket_status IN ('RESUELTO','CERRADO') THEN cast(1 + pmod(xxhash64(id, {seed + 33}), 5) AS INT) END AS csat_score,
           pmod(h1, 100) < 18 AS recontacto,
           TIMESTAMP('{anchor_date} 23:59:00') AS _ingested_at,
           cast(NULL AS STRING) AS _rescued_data
    FROM joined
    """,
    ticket_count,
)

write_table(
    "silver_nps",
    f"""
    WITH generated AS (
      SELECT id, pmod(id, {customer_count}) AS customer_idx,
             xxhash64(id, {seed + 40}) AS h0,
             xxhash64(id, {seed + 41}) AS h1
      FROM range({nps_count})
    ), joined AS (
      SELECT g.*, c.cliente_id, c.nps_ultimo,
             pmod(g.h0, 100) < 84 AS answered,
             cast(least(10, greatest(0, c.nps_ultimo + pmod(g.h1, 5) - 2)) AS INT) AS generated_score
      FROM generated g
      JOIN {fq}.silver_clientes c
        ON c.cliente_id = concat('CUS-DEMO-', lpad(cast(g.customer_idx + 1 AS STRING), 6, '0'))
    )
    SELECT concat('NPS-DEMO-', lpad(cast(id + 1 AS STRING), 8, '0')) AS nps_id,
           cliente_id,
           date_sub(DATE('{anchor_date}'), cast(pmod(h0, 365) AS INT)) AS fecha_encuesta,
           CASE WHEN answered THEN generated_score END AS score,
           CASE WHEN NOT answered THEN NULL WHEN generated_score <= 6 THEN 'DETRACTOR'
                WHEN generated_score <= 8 THEN 'PASSIVE' ELSE 'PROMOTER' END AS categoria_nps,
           element_at(array('SMS','EMAIL','APP'), cast(pmod(h1, 3) AS INT) + 1) AS canal_encuesta,
           answered AS respondida,
           TIMESTAMP('{anchor_date} 23:59:00') AS _ingested_at,
           cast(NULL AS STRING) AS _rescued_data
    FROM joined
    """,
    nps_count,
)

# COMMAND ----------

write_table(
    "silver_telemetria_red",
    f"""
    WITH hours AS (SELECT id AS hour_offset FROM range(72)),
    expanded AS (
      SELECT t.*, h.hour_offset,
             xxhash64(t.torre_id, h.hour_offset, {seed + 50}) AS sample_hash,
             timestampadd(HOUR, -cast(h.hour_offset AS INT), TIMESTAMP('{anchor_date} 23:00:00')) AS sample_ts
      FROM {fq}.bronze_torres_red t CROSS JOIN hours h
    ), load AS (
      SELECT *,
             least(0.99D, greatest(0.18D,
               0.38D + CASE WHEN hour(sample_ts) BETWEEN 18 AND 22 THEN 0.24D
                            WHEN hour(sample_ts) BETWEEN 8 AND 17 THEN 0.14D ELSE 0D END
               + pmod(sample_hash, 2300) / 10000D
               + CASE WHEN pmod(sample_hash, 100) < 7 THEN 0.24D ELSE 0D END
             )) AS load_ratio
      FROM expanded
    ), metrics AS (
      SELECT *,
             cast(least(capacidad_usuarios, round(capacidad_usuarios * load_ratio)) AS INT) AS connected,
             round(13D + load_ratio * 43D + CASE WHEN pmod(sample_hash, 100) < 7 THEN 38D ELSE 0D END, 2) AS latency,
             round(0.05D + load_ratio * 1.1D + CASE WHEN pmod(sample_hash, 100) < 7 THEN 2.6D ELSE 0D END, 3) AS loss,
             round(greatest(8D, (CASE tecnologia WHEN '5G' THEN 700D WHEN 'Fiber' THEN 950D ELSE 180D END) * (1.08D - load_ratio)), 2) AS throughput,
             round(36D + load_ratio * 31D + pmod(sample_hash, 1100) / 100D, 2) AS equipment_temp
      FROM load
    )
    SELECT torre_id, pais_codigo, ciudad, tecnologia,
           sample_ts AS timestamp,
           connected AS usuarios_conectados,
           capacidad_usuarios,
           round(100D * connected / capacidad_usuarios, 2) AS uso_capacidad_pct,
           latency AS latencia_ms,
           loss AS packet_loss_pct,
           throughput AS throughput_mbps,
           equipment_temp AS temperatura_equipo_c,
           CASE WHEN latency >= 75 OR loss >= 3.2 OR equipment_temp >= 82 THEN 'CRITICAL'
                WHEN load_ratio >= 0.82 OR latency >= 55 OR loss >= 1.5 THEN 'WARNING' ELSE 'OK' END AS alerta,
           TIMESTAMP('{anchor_date} 23:59:00') AS _ingested_at,
           cast(NULL AS STRING) AS _rescued_data
    FROM metrics
    """,
    telemetry_count,
)

write_table(
    "silver_cdrs",
    f"""
    WITH primary_subscription AS (
      SELECT cliente_id, suscripcion_id, plan_id,
             row_number() OVER (PARTITION BY cliente_id ORDER BY suscripcion_id) AS rn
      FROM {fq}.silver_suscripciones
    ), generated AS (
      SELECT id, pmod(id, {customer_count}) AS customer_idx,
             xxhash64(id, {seed + 60}) AS h0,
             xxhash64(id, {seed + 61}) AS h1
      FROM range({cdr_count})
    ), joined AS (
      SELECT g.*, c.cliente_id, c.pais_codigo, s.suscripcion_id, s.plan_id,
             element_at(array('VOICE','DATA','SMS'), cast(pmod(g.h0, 3) AS INT) + 1) AS event_type,
             -55D - pmod(g.h1, 66) AS signal
      FROM generated g
      JOIN {fq}.silver_clientes c
        ON c.cliente_id = concat('CUS-DEMO-', lpad(cast(g.customer_idx + 1 AS STRING), 6, '0'))
      JOIN primary_subscription s ON s.cliente_id = c.cliente_id AND s.rn = 1
    )
    SELECT concat('CDR-DEMO-', lpad(cast(id + 1 AS STRING), 10, '0')) AS cdr_id,
           cliente_id, suscripcion_id, plan_id, pais_codigo,
           date(timestampadd(MINUTE, -cast(pmod(h0, 129600) AS INT), TIMESTAMP('{anchor_date} 23:59:00'))) AS fecha,
           timestampadd(MINUTE, -cast(pmod(h0, 129600) AS INT), TIMESTAMP('{anchor_date} 23:59:00')) AS fecha_hora,
           event_type AS tipo_evento,
           CASE WHEN event_type = 'VOICE' THEN cast(10 + pmod(h1, 1791) AS INT) ELSE 0 END AS duracion_seg,
           CASE WHEN event_type = 'DATA' THEN round(1D + pmod(h1, 80000) / 100D, 2) ELSE 0D END AS datos_mb,
           CASE WHEN pmod(h0, 100) < 38 THEN '5G' ELSE '4G' END AS tecnologia_red,
           signal AS `calidad_señal_dbm`,
           event_type = 'VOICE' AND (signal <= -108 OR pmod(h0, 1000) < 18) AS llamada_caida,
           TIMESTAMP('{anchor_date} 23:59:00') AS _ingested_at,
           cast(NULL AS STRING) AS _rescued_data
    FROM joined
    """,
    cdr_count,
)

write_table(
    "silver_churn_features",
    f"""
    WITH subscriptions AS (
      SELECT cliente_id, count(*) AS total_suscripciones,
             sum(CASE WHEN estado = 'ACTIVA' THEN 1 ELSE 0 END) AS suscripciones_activas,
             round(sum(CASE WHEN estado = 'ACTIVA' THEN precio_mensual_usd ELSE 0D END), 2) AS gasto_mensual_total
      FROM {fq}.silver_suscripciones GROUP BY cliente_id
    ), invoices AS (
      SELECT cliente_id, count(*) AS total_facturas,
             sum(CASE WHEN estado_pago = 'vencida' THEN 1 ELSE 0 END) AS facturas_vencidas,
             round(avg(monto_total_usd), 2) AS avg_monto_factura,
             round(avg(dias_atraso), 2) AS avg_dias_atraso,
             max(dias_atraso) AS max_dias_atraso
      FROM {fq}.silver_facturas GROUP BY cliente_id
    ), tickets AS (
      SELECT cliente_id, count(*) AS total_tickets,
             sum(CASE WHEN categoria = 'CANCELACION' THEN 1 ELSE 0 END) AS tickets_cancelacion,
             sum(CASE WHEN recontacto THEN 1 ELSE 0 END) AS total_recontactos,
             round(avg(csat_score), 2) AS avg_csat
      FROM {fq}.silver_tickets GROUP BY cliente_id
    ), raw AS (
      SELECT c.*, s.total_suscripciones, s.suscripciones_activas, s.gasto_mensual_total,
             i.total_facturas, i.facturas_vencidas, i.avg_monto_factura, i.avg_dias_atraso, i.max_dias_atraso,
             t.total_tickets, t.tickets_cancelacion, t.total_recontactos, t.avg_csat,
             greatest(0.02D, least(0.97D,
               0.05D
               + 0.30D * i.facturas_vencidas / greatest(i.total_facturas, 1)
               + 0.18D * least(t.tickets_cancelacion, 3) / 3D
               + 0.12D * least(t.total_recontactos, 4) / 4D
               + 0.24D * (10D - c.nps_ultimo) / 10D
               + CASE WHEN s.suscripciones_activas = 0 THEN 0.20D ELSE 0D END
               + CASE WHEN c.estado <> 'ACTIVO' THEN 0.12D ELSE 0D END
               + CASE WHEN i.max_dias_atraso >= 30 THEN 0.08D ELSE 0D END
               - CASE WHEN c.credit_score >= 760 THEN 0.05D ELSE 0D END
             )) AS risk_score
      FROM {fq}.silver_clientes c
      JOIN subscriptions s USING (cliente_id)
      JOIN invoices i USING (cliente_id)
      JOIN tickets t USING (cliente_id)
    )
    SELECT cliente_id, pais_codigo, segmento_id, estado, edad, antiguedad_dias, credit_score,
           nps_ultimo, canal_adquisicion, total_suscripciones, suscripciones_activas,
           gasto_mensual_total, total_facturas, facturas_vencidas, avg_monto_factura,
           avg_dias_atraso, max_dias_atraso, total_tickets, tickets_cancelacion,
           total_recontactos, avg_csat,
           round(risk_score, 4) AS churn_risk_score,
           pmod(xxhash64(cliente_id, {seed + 70}), 10000) < cast(risk_score * 10000 AS BIGINT) AS churned,
           TIMESTAMP('{anchor_date} 23:59:00') AS _ingested_at,
           cast(NULL AS STRING) AS _rescued_data
    FROM raw
    """,
    customer_count,
)

# COMMAND ----------

write_table(
    "gold_churn_predictions",
    f"""
    SELECT cliente_id, pais_codigo, segmento_id, edad, antiguedad_dias, credit_score,
           nps_ultimo, suscripciones_activas, gasto_mensual_total, total_facturas,
           facturas_vencidas, total_tickets, tickets_cancelacion, churned,
           churn_risk_score AS churn_probability,
           churn_risk_score >= 0.50D AS churn_predicted,
           CASE WHEN churn_risk_score >= 0.85D THEN 'CRITICAL'
                WHEN churn_risk_score >= 0.65D THEN 'HIGH'
                WHEN churn_risk_score >= 0.40D THEN 'MEDIUM' ELSE 'LOW' END AS risk_tier,
           TIMESTAMP('{anchor_date} 23:59:00') AS scored_at
    FROM {fq}.silver_churn_features
    """,
    customer_count,
)

write_table(
    "gold_churn_risk_summary",
    f"""
    SELECT pais_codigo, segmento_id,
           CASE WHEN churn_risk_score >= 0.85D THEN 'CRITICAL'
                WHEN churn_risk_score >= 0.65D THEN 'HIGH'
                WHEN churn_risk_score >= 0.40D THEN 'MEDIUM' ELSE 'LOW' END AS riesgo_bucket,
           count(*) AS num_clientes,
           round(avg(churn_risk_score), 4) AS avg_risk_score,
           round(avg(gasto_mensual_total), 2) AS avg_gasto_mensual,
           round(avg(total_tickets), 2) AS avg_tickets,
           round(avg(avg_dias_atraso), 2) AS avg_dias_atraso,
           sum(CASE WHEN churned THEN 1 ELSE 0 END) AS ya_churned
    FROM {fq}.silver_churn_features
    GROUP BY pais_codigo, segmento_id, riesgo_bucket
    """,
)

write_table(
    "gold_clv_segments",
    f"""
    WITH base AS (
      SELECT *, facturas_vencidas / greatest(total_facturas, 1) AS ratio_vencidas,
             round(gasto_mensual_total * least(60D, greatest(6D, antiguedad_dias / 30D)) * (1D - churn_risk_score), 2) AS clv
      FROM {fq}.silver_churn_features
    )
    SELECT cliente_id, pais_codigo, segmento_id, estado, antiguedad_dias, credit_score,
           nps_ultimo, suscripciones_activas, total_suscripciones, gasto_mensual_total,
           round(ratio_vencidas, 4) AS ratio_vencidas, avg_dias_atraso,
           clv AS revenue_lifetime_est, churn_risk_score,
           CASE WHEN clv >= 5000D THEN 'CHAMPION' WHEN clv >= 2000D THEN 'HIGH_VALUE'
                WHEN clv >= 700D THEN 'GROWTH' ELSE 'VALUE_CARE' END AS segment,
           CASE WHEN clv >= 5000D THEN 'Campeones' WHEN clv >= 2000D THEN 'Alto valor'
                WHEN clv >= 700D THEN 'Crecimiento' ELSE 'Cuidado de valor' END AS segment_name,
           TIMESTAMP('{anchor_date} 23:59:00') AS scored_at
    FROM base
    """,
    customer_count,
)

write_table(
    "gold_customer_satisfaction",
    f"""
    WITH nps AS (
      SELECT trunc(n.fecha_encuesta, 'MM') AS mes, c.pais_codigo,
             count(CASE WHEN n.respondida THEN 1 END) AS total_encuestas,
             sum(CASE WHEN n.categoria_nps = 'PROMOTER' THEN 1 ELSE 0 END) AS promotores,
             sum(CASE WHEN n.categoria_nps = 'DETRACTOR' THEN 1 ELSE 0 END) AS detractores,
             round(100D * (sum(CASE WHEN n.categoria_nps = 'PROMOTER' THEN 1 ELSE 0 END)
                    - sum(CASE WHEN n.categoria_nps = 'DETRACTOR' THEN 1 ELSE 0 END))
                    / greatest(count(CASE WHEN n.respondida THEN 1 END), 1), 2) AS nps_index,
             round(avg(n.score), 2) AS avg_nps_score
      FROM {fq}.silver_nps n JOIN {fq}.silver_clientes c USING (cliente_id)
      GROUP BY trunc(n.fecha_encuesta, 'MM'), c.pais_codigo
    ), csat AS (
      SELECT trunc(date(fecha_creacion), 'MM') AS mes, pais_codigo,
             count(csat_score) AS total_evaluaciones_csat,
             round(avg(csat_score), 2) AS avg_csat,
             round(100D * sum(CASE WHEN csat_score >= 4 THEN 1 ELSE 0 END) / greatest(count(csat_score), 1), 2) AS csat_top2_pct
      FROM {fq}.silver_tickets GROUP BY trunc(date(fecha_creacion), 'MM'), pais_codigo
    )
    SELECT coalesce(n.mes, c.mes) AS mes, coalesce(n.pais_codigo, c.pais_codigo) AS pais_codigo,
           coalesce(n.total_encuestas, 0) AS total_encuestas,
           coalesce(n.promotores, 0) AS promotores, coalesce(n.detractores, 0) AS detractores,
           coalesce(n.nps_index, 0D) AS nps_index,
           coalesce(c.total_evaluaciones_csat, 0) AS total_evaluaciones_csat,
           coalesce(c.avg_csat, 0D) AS avg_csat, coalesce(c.csat_top2_pct, 0D) AS csat_top2_pct,
           coalesce(n.avg_nps_score, 0D) AS avg_nps_score
    FROM nps n FULL OUTER JOIN csat c ON n.mes = c.mes AND n.pais_codigo = c.pais_codigo
    """,
)

write_table(
    "gold_network_health",
    f"""
    SELECT timestamp AS hora, pais_codigo, count(*) AS total_mediciones,
           round(avg(latencia_ms), 2) AS avg_latencia_ms,
           round(avg(packet_loss_pct), 3) AS avg_packet_loss_pct,
           round(avg(throughput_mbps), 2) AS avg_throughput_mbps,
           round(avg(uso_capacidad_pct), 2) AS avg_uso_capacidad_pct,
           sum(CASE WHEN alerta <> 'OK' THEN 1 ELSE 0 END) AS torres_en_alerta,
           round(100D * sum(CASE WHEN alerta = 'OK' THEN 1 ELSE 0 END) / count(*), 2) AS uptime_pct
    FROM {fq}.silver_telemetria_red GROUP BY timestamp, pais_codigo
    """,
    telemetry_count // 20,
)

write_table(
    "gold_network_anomalies",
    f"""
    SELECT torre_id, pais_codigo, ciudad, tecnologia, timestamp, usuarios_conectados,
           uso_capacidad_pct, latencia_ms, packet_loss_pct, throughput_mbps,
           temperatura_equipo_c, alerta,
           alerta <> 'OK' AS is_anomaly,
           round(least(1D, greatest(0D,
             0.35D * uso_capacidad_pct / 100D + 0.30D * latencia_ms / 100D
             + 0.25D * packet_loss_pct / 5D + 0.10D * temperatura_equipo_c / 100D
           )), 4) AS anomaly_score,
           CASE WHEN alerta = 'CRITICAL' THEN 'CRITICAL' WHEN alerta = 'WARNING' THEN 'HIGH' ELSE 'NORMAL' END AS anomaly_severity,
           TIMESTAMP('{anchor_date} 23:59:00') AS scored_at
    FROM {fq}.silver_telemetria_red
    """,
    telemetry_count,
)

write_table(
    "gold_subscriber_metrics",
    f"""
    WITH months AS (
      SELECT explode(sequence(add_months(trunc(DATE('{anchor_date}'), 'MM'), -11), trunc(DATE('{anchor_date}'), 'MM'), interval 1 month)) AS mes
    ), dimensions AS (
      SELECT m.mes, p.pais_codigo, s.segmento_id
      FROM months m CROSS JOIN (SELECT DISTINCT pais_codigo FROM {fq}.silver_clientes) p
      CROSS JOIN {fq}.bronze_segmentos s
    ), customer_metrics AS (
      SELECT d.mes, d.pais_codigo, d.segmento_id,
             count(DISTINCT CASE WHEN c.fecha_alta <= last_day(d.mes) AND c.estado <> 'CANCELADO' THEN c.cliente_id END) AS clientes_activos
      FROM dimensions d LEFT JOIN {fq}.silver_clientes c
        ON c.pais_codigo = d.pais_codigo AND c.segmento_id = d.segmento_id
      GROUP BY d.mes, d.pais_codigo, d.segmento_id
    ), subscription_metrics AS (
      SELECT d.mes, d.pais_codigo, d.segmento_id,
             count(DISTINCT CASE WHEN s.fecha_inicio <= last_day(d.mes)
               AND (s.fecha_fin IS NULL OR s.fecha_fin > last_day(d.mes)) THEN s.suscripcion_id END) AS suscripciones_activas,
             count(DISTINCT CASE WHEN trunc(s.fecha_inicio, 'MM') = d.mes THEN s.suscripcion_id END) AS suscripciones_nuevas,
             count(DISTINCT CASE WHEN trunc(s.fecha_fin, 'MM') = d.mes THEN s.suscripcion_id END) AS suscripciones_canceladas
      FROM dimensions d
      LEFT JOIN {fq}.silver_clientes c ON c.pais_codigo = d.pais_codigo AND c.segmento_id = d.segmento_id
      LEFT JOIN {fq}.silver_suscripciones s ON s.cliente_id = c.cliente_id
      GROUP BY d.mes, d.pais_codigo, d.segmento_id
    )
    SELECT c.mes, c.pais_codigo, c.segmento_id, c.clientes_activos,
           s.suscripciones_activas, s.suscripciones_nuevas, s.suscripciones_canceladas,
           round(100D * s.suscripciones_canceladas / greatest(c.clientes_activos, 1), 3) AS tasa_churn_pct
    FROM customer_metrics c JOIN subscription_metrics s USING (mes, pais_codigo, segmento_id)
    """,
    12 * 12 * 3,
)

write_table(
    "gold_billing_health",
    f"""
    SELECT trunc(f.fecha_emision, 'MM') AS mes, c.pais_codigo,
           count(*) AS num_facturas,
           round(sum(f.monto_total_usd), 2) AS facturacion_total_usd,
           round(sum(CASE WHEN f.estado_pago = 'pagada' THEN f.monto_total_usd ELSE 0D END), 2) AS monto_pagado_usd,
           round(sum(CASE WHEN f.estado_pago = 'vencida' THEN f.monto_total_usd ELSE 0D END), 2) AS monto_vencido_usd,
           round(100D * sum(CASE WHEN f.estado_pago = 'pagada' THEN 1 ELSE 0 END) / count(*), 2) AS pct_pagada,
           round(100D * sum(CASE WHEN f.estado_pago = 'vencida' THEN 1 ELSE 0 END) / count(*), 2) AS pct_vencida,
           round(100D * sum(CASE WHEN f.estado_pago = 'pagada' THEN f.monto_total_usd ELSE 0D END) / greatest(sum(f.monto_total_usd), 0.01D), 2) AS tasa_cobro_pct,
           round(avg(f.dias_atraso), 2) AS avg_dias_atraso,
           round(sum(CASE WHEN f.estado_pago = 'vencida' THEN f.monto_total_usd ELSE 0D END), 2) AS cartera_vencida_usd
    FROM {fq}.silver_facturas f JOIN {fq}.silver_clientes c USING (cliente_id)
    GROUP BY trunc(f.fecha_emision, 'MM'), c.pais_codigo
    """,
    12 * 12,
)

write_table(
    "gold_revenue_by_country_service",
    f"""
    SELECT trunc(f.fecha_emision, 'MM') AS mes, c.pais_codigo, p.vertical,
           round(sum(f.monto_total_usd), 2) AS total_revenue_usd,
           round(sum(f.monto_total_usd), 2) AS ingresos_totales_usd,
           round(sum(CASE WHEN f.estado_pago = 'pagada' THEN f.monto_total_usd ELSE 0D END), 2) AS ingresos_cobrados_usd,
           count(*) AS num_facturas, count(DISTINCT f.cliente_id) AS unique_customers
    FROM {fq}.silver_facturas f
    JOIN {fq}.silver_suscripciones s USING (suscripcion_id, cliente_id)
    JOIN {fq}.bronze_planes p USING (plan_id)
    JOIN {fq}.silver_clientes c USING (cliente_id)
    GROUP BY trunc(f.fecha_emision, 'MM'), c.pais_codigo, p.vertical
    """,
    12 * 12 * 5,
)

write_table(
    "gold_arpu_by_segment",
    f"""
    SELECT trunc(f.fecha_emision, 'MM') AS mes, c.pais_codigo, c.segmento_id,
           round(sum(f.monto_total_usd), 2) AS total_revenue_usd,
           count(DISTINCT f.cliente_id) AS unique_customers,
           count(DISTINCT f.cliente_id) AS clientes_unicos,
           round(sum(f.monto_total_usd) / greatest(count(DISTINCT f.cliente_id), 1), 2) AS arpu_usd
    FROM {fq}.silver_facturas f JOIN {fq}.silver_clientes c USING (cliente_id)
    GROUP BY trunc(f.fecha_emision, 'MM'), c.pais_codigo, c.segmento_id
    """,
    12 * 12 * 3,
)

result = {
    "status": "GENERATED_PENDING_CERTIFICATION",
    "catalog": catalog,
    "schema": schema,
    "run_id": run_id,
    "customer_count": customer_count,
    "seed": seed,
    "anchor_date": anchor_date,
    "tables": generation_report,
    "total_rows": sum(int(item["rows"]) for item in generation_report),
}
dbutils.jobs.taskValues.set(key="generation_run_id", value=run_id)
print(json.dumps(result, ensure_ascii=False, indent=2))
