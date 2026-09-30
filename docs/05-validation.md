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

## Aceite funcional

1. App em estado `RUNNING`.
2. Preflight mostra Warehouse, Genie, AI Gateway, Lakebase, Memory, AI/BI, RBAC e grafo.
3. Genie cria nova conversa, responde e renderiza gráfico interativo.
4. Quetzal IQ mantém o contexto e diferencia dados internos de pesquisa externa.
5. Cliente 360 respeita escopo territorial e consentimento.
6. Dashboard AI/BI carrega no App.
7. Graph Intelligence só inicia pelo botão administrativo.
8. Voz do Cliente e Otimizador de Campanhas não executam comunicação real.

Guarde evidências sanitizadas conforme `docs/screenshots/README.md`.
