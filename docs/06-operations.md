# Operação

## Jobs

| Job | Frequência | Custo esperado |
|---|---|---|
| Bootstrap operacional | manual, instalação/mudança de schema | baixo |
| Managed Memory Foundation | manual | baixo |
| Motor de alertas | manual pelo App | baixo |
| Graph Intelligence | manual e aprovado | maior |

Nenhum job deve receber `schedule` ou `trigger` sem uma mudança revisada.

## Logs

```bash
databricks apps logs "$BUNDLE_VAR_app_name" --tail-lines 500 --profile "$DATABRICKS_CONFIG_PROFILE"
```

Não copie payloads contendo PII para issues. Use trace IDs, run IDs e mensagens redigidas.

## Conectores e egress

CRM/BSS/OSS e pesquisa externa iniciam desabilitados. Habilite-os somente após allowlist de destino, segredo em cofre do cliente, timeout, idempotência e aprovação humana.
