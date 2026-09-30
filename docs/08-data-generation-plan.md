# Plano de geração sintética telecom

**Tier:** 3 · notebook serverless com Spark SQL/Catalyst  
**Seed:** 42  
**Compute:** Serverless, somente quando o job manual for executado  
**Output:** `${catalog}.${schema}.*`  
**Volume:** 369.568 linhas canônicas com 10 mil clientes, antes das derivações gold e do Graph Intelligence

Nenhum nome, e-mail ou telefone representa uma pessoa real. Identidades seguem `Cliente Demo 000001`, `customer000001@example.com` e números deliberadamente não roteáveis.

## Tabelas de referência

### `bronze_segmentos` — 3 linhas

| Coluna | Tipo | Geração |
|---|---|---|
| `segmento_id` | STRING | `PER`, `COM`, `ENT`; chave primária |
| `segmento_nombre` | STRING | Personal, Comercial, Empresarial |
| `marca_comercial` | STRING | marcas fictícias Quetzal |

### `bronze_planes` — 45 linhas

| Coluna | Tipo | Geração |
|---|---|---|
| `plan_id` | STRING | determinístico por segmento e sequência |
| `nombre` | STRING | nome fictício do produto |
| `vertical` | STRING | Móvil, Internet, TV, Fija ou Bundles |
| `tier` | STRING | Essential, Plus ou Max |
| `segmento` | STRING | FK para `bronze_segmentos.segmento_id` |
| `precio_usd` | DOUBLE | faixa coerente por segmento/tier |
| `data_gb` | DOUBLE | nulo para produtos não móveis |
| `internet_mbps` | INT | nulo para produtos sem banda larga |
| `minutos` | INT | nulo para produtos sem voz |
| `tv_canales` | INT | nulo para produtos sem TV |
| `es_bundle` | BOOLEAN | verdadeiro apenas para Bundles |

### `bronze_torres_red` — 240 linhas

| Coluna | Tipo | Geração |
|---|---|---|
| `torre_id` | STRING | chave determinística |
| `pais_codigo` | STRING | 12 códigos ISO-2 LATAM |
| `ciudad` | STRING | cidades fictícias por mercado |
| `latitud` | DOUBLE | centro do país + ruído determinístico |
| `longitud` | DOUBLE | centro do país + ruído determinístico |
| `tecnologia` | STRING | 4G, 5G ou Fiber |
| `capacidad_usuarios` | INT | 500–5000 |

## Tabelas silver

### `silver_clientes` — 10.000 linhas

| Coluna | Tipo | Geração |
|---|---|---|
| `cliente_id` | STRING | `CUS-DEMO-` + sequência; PK |
| `nombre`, `apellido_1`, `apellido_2`, `nombre_completo` | STRING | identidade explicitamente sintética |
| `email` | STRING | domínio `example.com` |
| `telefono` | STRING | número não roteável |
| `fecha_nacimiento`, `edad` | DATE, INT | 18–85 anos, consistentes |
| `sexo` | STRING | F, M, X |
| `pais_codigo` | STRING | distribuição nos 12 mercados |
| `segmento_id` | STRING | FK ponderada PER/COM/ENT |
| `fecha_alta`, `antiguedad_dias` | DATE, INT | últimos 8 anos, consistentes |
| `estado` | STRING | ACTIVO, SUSPENDIDO ou CANCELADO |
| `canal_adquisicion` | STRING | DIGITAL, TIENDA, PARTNER, CALL_CENTER |
| `credit_score` | INT | 300–850 |
| `nps_ultimo` | INT | 0–10 |
| `acepta_marketing` | BOOLEAN | 72% verdadeiro, independente do canal |
| `_ingested_at` | TIMESTAMP | timestamp de execução |
| `_rescued_data` | STRING | sempre nulo no modo sintético |

### `silver_suscripciones` — 14.000 linhas

| Coluna | Tipo | Geração |
|---|---|---|
| `suscripcion_id` | STRING | PK determinística |
| `cliente_id` | STRING | FK para cliente |
| `plan_id` | STRING | FK compatível com segmento |
| `estado` | STRING | ACTIVA, CANCELADA ou SUSPENDIDA |
| `fecha_inicio`, `fecha_fin` | DATE | intervalo consistente; fim pode ser nulo |
| `precio_mensual_usd` | DOUBLE | preço do plano com desconto limitado |
| `metodo_pago` | STRING | CARD, DEBIT, INVOICE, CASH |
| `auto_renovacion` | BOOLEAN | ponderado por método de pagamento |

### `silver_facturas` — 168.000 linhas

| Coluna | Tipo | Geração |
|---|---|---|
| `factura_id` | STRING | PK determinística |
| `suscripcion_id`, `cliente_id` | STRING | FKs consistentes |
| `fecha_emision`, `fecha_vencimiento`, `fecha_pago` | DATE | 12 meses; pagamento pode ser nulo |
| `monto_base_usd`, `ajustes_usd`, `monto_total_usd` | DOUBLE | total = base + ajuste |
| `estado_pago` | STRING | pagada, pendiente ou vencida |
| `dias_atraso` | INT | zero ou diferença coerente |

### `silver_tickets` — 18.000 linhas

| Coluna | Tipo | Geração |
|---|---|---|
| `ticket_id` | STRING | PK determinística |
| `cliente_id` | STRING | FK para cliente |
| `fecha_creacion` | TIMESTAMP | últimos 180 dias |
| `categoria`, `motivo` | STRING | rede, cobrança, cancelamento, produto |
| `canal` | STRING | APP, CALL, CHAT, STORE |
| `pais_codigo` | STRING | herdado do cliente |
| `prioridad` | STRING | LOW, MEDIUM, HIGH, CRITICAL |
| `estado` | STRING | ABIERTO, EN_PROGRESO, RESUELTO, CERRADO |
| `tiempo_resolucion_horas` | DOUBLE | nulo enquanto aberto |
| `csat_score` | INT | 1–5; nulo sem resolução |
| `recontacto` | BOOLEAN | maior em falhas prolongadas |
| `_ingested_at`, `_rescued_data` | TIMESTAMP, STRING | execução; nulo |

### `silver_nps` — 12.000 linhas

| Coluna | Tipo | Geração |
|---|---|---|
| `nps_id` | STRING | PK determinística |
| `cliente_id` | STRING | FK para cliente |
| `fecha_encuesta` | DATE | últimos 12 meses |
| `score` | INT | 0–10 |
| `categoria_nps` | STRING | DETRACTOR, PASSIVE, PROMOTER derivado do score |
| `canal_encuesta` | STRING | SMS, EMAIL, APP |
| `respondida` | BOOLEAN | controla score nulo |
| `_ingested_at`, `_rescued_data` | TIMESTAMP, STRING | execução; nulo |

### `silver_telemetria_red` — 17.280 linhas

| Coluna | Tipo | Geração |
|---|---|---|
| `torre_id`, `pais_codigo`, `ciudad`, `tecnologia` | STRING | herdados da torre |
| `timestamp` | TIMESTAMP | 72 snapshots horários |
| `usuarios_conectados` | INT | sazonalidade horária, limitado à capacidade |
| `capacidad_usuarios` | INT | herdada da torre |
| `uso_capacidad_pct` | DOUBLE | conectados/capacidade |
| `latencia_ms`, `packet_loss_pct`, `throughput_mbps` | DOUBLE | degradam com capacidade |
| `temperatura_equipo_c` | DOUBLE | 35–95 °C |
| `alerta` | STRING | derivada de capacidade, latência, perda e temperatura |
| `_ingested_at`, `_rescued_data` | TIMESTAMP, STRING | execução; nulo |

### `silver_cdrs` — 120.000 linhas

| Coluna | Tipo | Geração |
|---|---|---|
| `cdr_id` | STRING | PK determinística |
| `cliente_id`, `suscripcion_id`, `plan_id` | STRING | FKs consistentes |
| `pais_codigo` | STRING | herdado do cliente |
| `fecha`, `fecha_hora` | DATE, TIMESTAMP | últimos 90 dias |
| `tipo_evento` | STRING | VOICE, DATA, SMS |
| `duracion_seg`, `datos_mb` | INT, DOUBLE | condicionado ao tipo |
| `tecnologia_red` | STRING | 4G ou 5G |
| `calidad_señal_dbm` | DOUBLE | -120 a -55 |
| `llamada_caida` | BOOLEAN | correlacionada à qualidade |
| `_ingested_at`, `_rescued_data` | TIMESTAMP, STRING | execução; nulo |

### `silver_churn_features` — 10.000 linhas

| Coluna | Tipo | Geração |
|---|---|---|
| `cliente_id`, `pais_codigo`, `segmento_id`, `estado` | STRING | herdados do cliente |
| `edad`, `antiguedad_dias`, `credit_score`, `nps_ultimo` | INT | herdados |
| `canal_adquisicion` | STRING | herdado |
| `total_suscripciones`, `suscripciones_activas` | INT | agregados de assinaturas |
| `gasto_mensual_total` | DOUBLE | assinatura ativa |
| `total_facturas`, `facturas_vencidas` | INT | agregados de faturas |
| `avg_monto_factura`, `avg_dias_atraso`, `max_dias_atraso` | DOUBLE | agregados coerentes |
| `total_tickets`, `tickets_cancelacion`, `total_recontactos` | INT | agregados de suporte |
| `avg_csat` | DOUBLE | suporte resolvido |
| `churn_risk_score` | DOUBLE | fórmula transparente 0–1 |
| `churned` | BOOLEAN | evento sintético correlacionado, não inferência causal |
| `_ingested_at`, `_rescued_data` | TIMESTAMP, STRING | execução; nulo |

## Derivações gold

O mesmo job deriva, sem aleatoriedade adicional:

| Tabela | Colunas completas | Derivação |
|---|---|---|
| `gold_churn_predictions` | `cliente_id`, `pais_codigo`, `segmento_id`, `edad`, `antiguedad_dias`, `credit_score`, `nps_ultimo`, `suscripciones_activas`, `gasto_mensual_total`, `total_facturas`, `facturas_vencidas`, `total_tickets`, `tickets_cancelacion`, `churned`, `churn_probability`, `churn_predicted`, `risk_tier`, `scored_at` | score logístico transparente sobre features |
| `gold_churn_risk_summary` | `pais_codigo`, `segmento_id`, `riesgo_bucket`, `num_clientes`, `avg_risk_score`, `avg_gasto_mensual`, `avg_tickets`, `avg_dias_atraso`, `ya_churned` | agregado do churn |
| `gold_clv_segments` | `cliente_id`, `pais_codigo`, `segmento_id`, `estado`, `antiguedad_dias`, `credit_score`, `nps_ultimo`, `suscripciones_activas`, `total_suscripciones`, `gasto_mensual_total`, `ratio_vencidas`, `avg_dias_atraso`, `revenue_lifetime_est`, `churn_risk_score`, `segment`, `segment_name`, `scored_at` | gasto, tenure e risco |
| `gold_customer_satisfaction` | `mes`, `pais_codigo`, `total_encuestas`, `promotores`, `detractores`, `nps_index`, `total_evaluaciones_csat`, `avg_csat`, `csat_top2_pct`, `avg_nps_score` | NPS + tickets |
| `gold_network_health` | `hora`, `pais_codigo`, `total_mediciones`, `avg_latencia_ms`, `avg_packet_loss_pct`, `avg_throughput_mbps`, `avg_uso_capacidad_pct`, `torres_en_alerta`, `uptime_pct` | telemetria horária |
| `gold_network_anomalies` | `torre_id`, `pais_codigo`, `ciudad`, `tecnologia`, `timestamp`, `usuarios_conectados`, `uso_capacidad_pct`, `latencia_ms`, `packet_loss_pct`, `throughput_mbps`, `temperatura_equipo_c`, `alerta`, `is_anomaly`, `anomaly_score`, `anomaly_severity`, `scored_at` | regras transparentes, não Isolation Forest |
| `gold_subscriber_metrics` | `mes`, `pais_codigo`, `segmento_id`, `clientes_activos`, `suscripciones_activas`, `suscripciones_nuevas`, `suscripciones_canceladas`, `tasa_churn_pct` | clientes + assinaturas |
| `gold_billing_health` | `mes`, `pais_codigo`, `num_facturas`, `facturacion_total_usd`, `monto_pagado_usd`, `monto_vencido_usd`, `pct_pagada`, `pct_vencida`, `tasa_cobro_pct`, `avg_dias_atraso`, `cartera_vencida_usd` | faturas |
| `gold_revenue_by_country_service` | `mes`, `pais_codigo`, `vertical`, `total_revenue_usd`, `ingresos_totales_usd`, `ingresos_cobrados_usd`, `num_facturas`, `unique_customers` | faturas + assinaturas + planos |
| `gold_arpu_by_segment` | `mes`, `pais_codigo`, `segmento_id`, `total_revenue_usd`, `unique_customers`, `clientes_unicos`, `arpu_usd` | receita/clientes únicos |

## Relações

- assinaturas → clientes e planos;
- faturas → assinaturas e clientes;
- tickets, NPS e CDRs → clientes;
- telemetria → torres;
- churn e CLV → clientes.

## Controles de execução

- criação do schema somente quando autorizado;
- overwrite apenas no modo sintético e apenas no schema configurado;
- validação de identificadores e volumes antes de qualquer escrita;
- `data_classification=synthetic` em todas as tabelas;
- job sem schedule, `max_concurrent_runs=1`;
- certificação bloqueante com fingerprint determinístico, integridade referencial e cobertura das jornadas da demo;
- resumo final com volumes, seed e timestamps.
