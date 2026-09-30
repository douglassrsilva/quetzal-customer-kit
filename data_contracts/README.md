# Contrato canônico de dados

O App consulta somente o modelo canônico neste schema. Clientes podem preenchê-lo com o gerador sintético aprovado ou com views de adaptação sobre fontes governadas.

## Fontes obrigatórias

| Domínio | Tabelas |
|---|---|
| Referência | `bronze_segmentos`, `bronze_planes`, `bronze_torres_red` |
| Cliente | `silver_clientes`, `silver_suscripciones` |
| Receita | `silver_facturas` |
| Experiência | `silver_tickets`, `silver_nps`, `silver_cdrs` |
| Rede | `silver_telemetria_red` |
| ML | `silver_churn_features`, `gold_churn_predictions`, `gold_clv_segments` |

As demais tabelas `gold_*`, `mv_*` e `ops_*` são derivadas. Chaves principais não devem ser reutilizadas entre ambientes. Campos de PII exigem masking e acesso territorial no modo customer.

O plano completo da carga sintética está em [docs/08-data-generation-plan.md](../docs/08-data-generation-plan.md).
