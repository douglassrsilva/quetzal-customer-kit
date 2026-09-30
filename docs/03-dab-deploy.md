# Deploy com Databricks Asset Bundles

## Configuração

```bash
cp config/customer.env.example config/customer.env
make preflight
make render
```

`render` injeta catálogo, schema e URI da ontologia somente nos artefatos gerados. Os templates versionados continuam neutros.

## Validação e deploy

```bash
make frontend-build
make bundle-validate TARGET=dev
make bundle-deploy TARGET=dev
```

Os IDs de App, dashboard, Genie Spaces e jobs são resolvidos pelas referências do bundle. Não copie IDs de outro workspace e não use sync manual como etapa final.

## Promoção

Use um `config/customer.env` específico por ambiente e um GitHub Environment protegido para `staging` e `prod`. O workflow de deploy é manual e usa OIDC; não armazene PAT ou client secret no repositório.
