# Plan de generación sintética para telecomunicaciones

**Tier:** 3 · notebook serverless com Spark SQL/Catalyst  
**Seed:** 42  
**Cómputo:** Serverless, únicamente cuando se ejecute el job manual  
**Output:** `${catalog}.${schema}.*`  
**Volumen:** 369.568 filas canónicas con 10.000 clientes, antes de las derivaciones gold y de Graph Intelligence

Ningún nombre, correo o teléfono representa a una persona real. Las identidades siguen el patrón `Cliente Demo 000001`, `customer000001@example.com` y números deliberadamente no enrutables.

## Tablas de referencia

### `bronze_segmentos` — 3 filas

| Columna | Tipo | Generación |
|---|---|---|
| `segmento_id` | STRING | `PER`, `COM`, `ENT`; clave primaria |
| `segmento_nombre` | STRING | Personal, Comercial, Empresarial |
| `marca_comercial` | STRING | marcas ficticias de Quetzal |

### `bronze_planes` — 45 filas

| Columna | Tipo | Generación |
|---|---|---|
| `plan_id` | STRING | determinista por segmento y secuencia |
| `nombre` | STRING | nombre ficticio del producto |
| `vertical` | STRING | Móvil, Internet, TV, Fija o Bundles |
| `tier` | STRING | Essential, Plus o Max |
| `segmento` | STRING | FK para `bronze_segmentos.segmento_id` |
| `precio_usd` | DOUBLE | rango coherente por segmento y tier |
| `data_gb` | DOUBLE | nulo para productos que no son móviles |
| `internet_mbps` | INT | nulo para productos sin banda ancha |
| `minutos` | INT | nulo para productos sin voz |
| `tv_canales` | INT | nulo para productos sin TV |
| `es_bundle` | BOOLEAN | verdadero únicamente para Bundles |

### `bronze_torres_red` — 240 filas

| Columna | Tipo | Generación |
|---|---|---|
| `torre_id` | STRING | clave determinista |
| `pais_codigo` | STRING | 12 códigos ISO-2 de LATAM |
| `ciudad` | STRING | ciudades ficticias por mercado |
| `latitud` | DOUBLE | centro del país + ruido determinista |
| `longitud` | DOUBLE | centro del país + ruido determinista |
| `tecnologia` | STRING | 4G, 5G o Fiber |
| `capacidad_usuarios` | INT | 500–5000 |

## Tablas silver

### `silver_clientes` — 10.000 filas

| Columna | Tipo | Generación |
|---|---|---|
| `cliente_id` | STRING | `CUS-DEMO-` + secuencia; PK |
| `nombre`, `apellido_1`, `apellido_2`, `nombre_completo` | STRING | identidad explícitamente sintética |
| `email` | STRING | dominio `example.com` |
| `telefono` | STRING | número no enrutable |
| `fecha_nacimiento`, `edad` | DATE, INT | 18–85 años, consistentes |
| `sexo` | STRING | F, M, X |
| `pais_codigo` | STRING | distribución en los 12 mercados |
| `segmento_id` | STRING | FK ponderada PER/COM/ENT |
| `fecha_alta`, `antiguedad_dias` | DATE, INT | últimos 8 años, consistentes |
| `estado` | STRING | ACTIVO, SUSPENDIDO o CANCELADO |
| `canal_adquisicion` | STRING | DIGITAL, TIENDA, PARTNER, CALL_CENTER |
| `credit_score` | INT | 300–850 |
| `nps_ultimo` | INT | 0–10 |
| `acepta_marketing` | BOOLEAN | 72% verdadero, independiente del canal |
| `_ingested_at` | TIMESTAMP | timestamp de ejecución |
| `_rescued_data` | STRING | siempre nulo en el modo sintético |

### `silver_suscripciones` — 14.000 filas

| Columna | Tipo | Generación |
|---|---|---|
| `suscripcion_id` | STRING | PK determinista |
| `cliente_id` | STRING | FK al cliente |
| `plan_id` | STRING | FK compatible con el segmento |
| `estado` | STRING | ACTIVA, CANCELADA o SUSPENDIDA |
| `fecha_inicio`, `fecha_fin` | DATE | intervalo consistente; el fin puede ser nulo |
| `precio_mensual_usd` | DOUBLE | precio del plan con descuento limitado |
| `metodo_pago` | STRING | CARD, DEBIT, INVOICE o CASH |
| `auto_renovacion` | BOOLEAN | ponderado por método de pago |

### `silver_facturas` — 168.000 filas

| Columna | Tipo | Generación |
|---|---|---|
| `factura_id` | STRING | PK determinista |
| `suscripcion_id`, `cliente_id` | STRING | FKs consistentes |
| `fecha_emision`, `fecha_vencimiento`, `fecha_pago` | DATE | 12 meses; el pago puede ser nulo |
| `monto_base_usd`, `ajustes_usd`, `monto_total_usd` | DOUBLE | total = base + ajuste |
| `estado_pago` | STRING | pagada, pendiente o vencida |
| `dias_atraso` | INT | cero o diferencia coherente |

### `silver_tickets` — 18.000 filas

| Columna | Tipo | Generación |
|---|---|---|
| `ticket_id` | STRING | PK determinista |
| `cliente_id` | STRING | FK al cliente |
| `fecha_creacion` | TIMESTAMP | últimos 180 días |
| `categoria`, `motivo` | STRING | red, facturación, cancelación o producto |
| `canal` | STRING | APP, CALL, CHAT, STORE |
| `pais_codigo` | STRING | heredado del cliente |
| `prioridad` | STRING | LOW, MEDIUM, HIGH, CRITICAL |
| `estado` | STRING | ABIERTO, EN_PROGRESO, RESUELTO, CERRADO |
| `tiempo_resolucion_horas` | DOUBLE | nulo mientras esté abierto |
| `csat_score` | INT | 1–5; nulo sin resolución |
| `recontacto` | BOOLEAN | mayor en fallas prolongadas |
| `_ingested_at`, `_rescued_data` | TIMESTAMP, STRING | ejecución; nulo |

### `silver_nps` — 12.000 filas

| Columna | Tipo | Generación |
|---|---|---|
| `nps_id` | STRING | PK determinista |
| `cliente_id` | STRING | FK al cliente |
| `fecha_encuesta` | DATE | últimos 12 meses |
| `score` | INT | 0–10 |
| `categoria_nps` | STRING | DETRACTOR, PASSIVE o PROMOTER derivado del score |
| `canal_encuesta` | STRING | SMS, EMAIL, APP |
| `respondida` | BOOLEAN | controla el score nulo |
| `_ingested_at`, `_rescued_data` | TIMESTAMP, STRING | ejecución; nulo |

### `silver_telemetria_red` — 17.280 filas

| Columna | Tipo | Generación |
|---|---|---|
| `torre_id`, `pais_codigo`, `ciudad`, `tecnologia` | STRING | heredados de la torre |
| `timestamp` | TIMESTAMP | 72 snapshots horarios |
| `usuarios_conectados` | INT | estacionalidad horaria, limitado por la capacidad |
| `capacidad_usuarios` | INT | heredada de la torre |
| `uso_capacidad_pct` | DOUBLE | conectados/capacidad |
| `latencia_ms`, `packet_loss_pct`, `throughput_mbps` | DOUBLE | se degradan con la capacidad |
| `temperatura_equipo_c` | DOUBLE | 35–95 °C |
| `alerta` | STRING | derivada de capacidad, latencia, pérdida y temperatura |
| `_ingested_at`, `_rescued_data` | TIMESTAMP, STRING | ejecución; nulo |

### `silver_cdrs` — 120.000 filas

| Columna | Tipo | Generación |
|---|---|---|
| `cdr_id` | STRING | PK determinista |
| `cliente_id`, `suscripcion_id`, `plan_id` | STRING | FKs consistentes |
| `pais_codigo` | STRING | heredado del cliente |
| `fecha`, `fecha_hora` | DATE, TIMESTAMP | últimos 90 días |
| `tipo_evento` | STRING | VOICE, DATA, SMS |
| `duracion_seg`, `datos_mb` | INT, DOUBLE | condicionado por el tipo |
| `tecnologia_red` | STRING | 4G o 5G |
| `calidad_señal_dbm` | DOUBLE | -120 a -55 |
| `llamada_caida` | BOOLEAN | correlacionada con la calidad |
| `_ingested_at`, `_rescued_data` | TIMESTAMP, STRING | ejecución; nulo |

### `silver_churn_features` — 10.000 filas

| Columna | Tipo | Generación |
|---|---|---|
| `cliente_id`, `pais_codigo`, `segmento_id`, `estado` | STRING | heredados del cliente |
| `edad`, `antiguedad_dias`, `credit_score`, `nps_ultimo` | INT | heredados |
| `canal_adquisicion` | STRING | heredado |
| `total_suscripciones`, `suscripciones_activas` | INT | agregados de suscripciones |
| `gasto_mensual_total` | DOUBLE | suscripción activa |
| `total_facturas`, `facturas_vencidas` | INT | agregados de facturas |
| `avg_monto_factura`, `avg_dias_atraso`, `max_dias_atraso` | DOUBLE | agregados coherentes |
| `total_tickets`, `tickets_cancelacion`, `total_recontactos` | INT | agregados de soporte |
| `avg_csat` | DOUBLE | soporte resuelto |
| `churn_risk_score` | DOUBLE | fórmula transparente entre 0 y 1 |
| `churned` | BOOLEAN | evento sintético correlacionado, no inferencia causal |
| `_ingested_at`, `_rescued_data` | TIMESTAMP, STRING | ejecución; nulo |

## Derivaciones gold

El mismo job deriva, sin aleatoriedad adicional:

| Tabla | Columnas completas | Derivación |
|---|---|---|
| `gold_churn_predictions` | `cliente_id`, `pais_codigo`, `segmento_id`, `edad`, `antiguedad_dias`, `credit_score`, `nps_ultimo`, `suscripciones_activas`, `gasto_mensual_total`, `total_facturas`, `facturas_vencidas`, `total_tickets`, `tickets_cancelacion`, `churned`, `churn_probability`, `churn_predicted`, `risk_tier`, `scored_at` | score logístico transparente sobre features |
| `gold_churn_risk_summary` | `pais_codigo`, `segmento_id`, `riesgo_bucket`, `num_clientes`, `avg_risk_score`, `avg_gasto_mensual`, `avg_tickets`, `avg_dias_atraso`, `ya_churned` | agregado de churn |
| `gold_clv_segments` | `cliente_id`, `pais_codigo`, `segmento_id`, `estado`, `antiguedad_dias`, `credit_score`, `nps_ultimo`, `suscripciones_activas`, `total_suscripciones`, `gasto_mensual_total`, `ratio_vencidas`, `avg_dias_atraso`, `revenue_lifetime_est`, `churn_risk_score`, `segment`, `segment_name`, `scored_at` | gasto, antigüedad y riesgo |
| `gold_customer_satisfaction` | `mes`, `pais_codigo`, `total_encuestas`, `promotores`, `detractores`, `nps_index`, `total_evaluaciones_csat`, `avg_csat`, `csat_top2_pct`, `avg_nps_score` | NPS + tickets |
| `gold_network_health` | `hora`, `pais_codigo`, `total_mediciones`, `avg_latencia_ms`, `avg_packet_loss_pct`, `avg_throughput_mbps`, `avg_uso_capacidad_pct`, `torres_en_alerta`, `uptime_pct` | telemetría horaria |
| `gold_network_anomalies` | `torre_id`, `pais_codigo`, `ciudad`, `tecnologia`, `timestamp`, `usuarios_conectados`, `uso_capacidad_pct`, `latencia_ms`, `packet_loss_pct`, `throughput_mbps`, `temperatura_equipo_c`, `alerta`, `is_anomaly`, `anomaly_score`, `anomaly_severity`, `scored_at` | reglas transparentes, no Isolation Forest |
| `gold_subscriber_metrics` | `mes`, `pais_codigo`, `segmento_id`, `clientes_activos`, `suscripciones_activas`, `suscripciones_nuevas`, `suscripciones_canceladas`, `tasa_churn_pct` | clientes + suscripciones |
| `gold_billing_health` | `mes`, `pais_codigo`, `num_facturas`, `facturacion_total_usd`, `monto_pagado_usd`, `monto_vencido_usd`, `pct_pagada`, `pct_vencida`, `tasa_cobro_pct`, `avg_dias_atraso`, `cartera_vencida_usd` | facturas |
| `gold_revenue_by_country_service` | `mes`, `pais_codigo`, `vertical`, `total_revenue_usd`, `ingresos_totales_usd`, `ingresos_cobrados_usd`, `num_facturas`, `unique_customers` | facturas + suscripciones + planes |
| `gold_arpu_by_segment` | `mes`, `pais_codigo`, `segmento_id`, `total_revenue_usd`, `unique_customers`, `clientes_unicos`, `arpu_usd` | ingresos/clientes únicos |

## Relaciones

- suscripciones → clientes y planes;
- facturas → suscripciones y clientes;
- tickets, NPS y CDRs → clientes;
- telemetría → torres;
- churn y CLV → clientes.

## Controles de ejecución

- creación del esquema únicamente cuando esté autorizada;
- overwrite solo en modo sintético y únicamente en el esquema configurado;
- validación de identificadores y volúmenes antes de cualquier escritura;
- `data_classification=synthetic` en todas las tablas;
- job sin programación, con `max_concurrent_runs=1`;
- certificación bloqueante con fingerprint determinista, integridad referencial y cobertura de los flujos funcionales;
- resumen final con volúmenes, seed y timestamps.
