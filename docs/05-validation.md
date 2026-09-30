# Validação

## Local e CI

```bash
make sanitize
python -m pytest -q
make frontend-build
terraform -chdir=terraform/environments/dev fmt -check -recursive
terraform -chdir=terraform/environments/dev validate
make bundle-validate TARGET=dev
```

## Certificação dos dados sintéticos

```bash
make synthetic-data TARGET=dev
```

O job possui duas tarefas encadeadas. A primeira gera as fontes e derivações; a segunda bloqueia o sucesso até comprovar:

- contagens e schemas esperados;
- chaves primárias e integridade referencial;
- PII exclusivamente fictícia e não roteável;
- coerência de datas, faturas, NPS, telemetria e churn;
- cobertura de Cliente 360, SLA, retenção, campanhas, Voz do Cliente e incidentes de rede;
- propriedades `data_classification=synthetic` e `generated_by=quetzal-customer-kit`;
- fingerprint estável para os mesmos `customer_count`, `seed` e `anchor_date`.

Uma execução verde é a evidência funcional do dataset. `bundle validate` isoladamente comprova apenas a configuração do DAB.

## Aceite funcional

1. Job sintético em `SUCCEEDED`, com tarefa de certificação concluída.
2. App em estado `RUNNING`.
3. Preflight mostra Warehouse, Genie, AI Gateway, Lakebase, Memory, AI/BI, RBAC e grafo.
4. Genie cria nova conversa, responde e renderiza gráfico interativo.
5. Quetzal IQ mantém o contexto e diferencia dados internos de pesquisa externa.
6. Cliente 360 respeita escopo territorial e consentimento.
7. Dashboard AI/BI carrega no App.
8. Graph Intelligence só inicia pelo botão administrativo.
9. Voz do Cliente e Otimizador de Campanhas não executam comunicação real.

Guarde evidências sanitizadas conforme `docs/screenshots/README.md`.
