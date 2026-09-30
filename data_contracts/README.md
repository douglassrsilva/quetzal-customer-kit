# Contrato canónico de datos

La aplicación consulta únicamente el modelo canónico de este esquema. El cliente puede poblarlo con el generador sintético aprobado o con vistas de adaptación sobre fuentes gobernadas.

## Fuentes obligatorias

| Dominio | Tablas |
|---|---|
| Referencia | `bronze_segmentos`, `bronze_planes`, `bronze_torres_red` |
| Cliente | `silver_clientes`, `silver_suscripciones` |
| Ingresos | `silver_facturas` |
| Experiencia | `silver_tickets`, `silver_nps`, `silver_cdrs` |
| Red | `silver_telemetria_red` |
| ML | `silver_churn_features`, `gold_churn_predictions`, `gold_clv_segments` |

Las demás tablas `gold_*`, `mv_*` y `ops_*` son derivadas. Las claves principales no deben reutilizarse entre entornos. Los campos con PII requieren enmascaramiento y acceso territorial en el modo `customer`.

El plan completo de la carga sintética se encuentra en [docs/08-data-generation-plan.md](../docs/08-data-generation-plan.md).
