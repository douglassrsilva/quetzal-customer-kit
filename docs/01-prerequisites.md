# Pré-requisitos

## Acessos

- workspace Databricks com serverless, Unity Catalog, Apps, AI/BI e Genie habilitados;
- permissão para usar ou criar schema, Warehouse e grupos;
- projeto Lakebase Autoscaling, branch e endpoint aprovados;
- model service do Unity AI Gateway aprovado;
- administrador capaz de configurar federação OIDC do GitHub para o Databricks;
- grupos separados para usuários e administradores do Quetzal.

## Ferramentas locais

```bash
python --version       # 3.11+
node --version         # 20+
terraform version      # 1.7+
databricks -v          # 0.229+
```

Autentique localmente com OAuth U2M:

```bash
databricks auth login --host https://customer-workspace.cloud.databricks.com --profile customer-dev
databricks current-user me --profile customer-dev
```

Não use PAT em `config/customer.env`. O arquivo aceita apenas identificadores não secretos e é ignorado pelo Git.
