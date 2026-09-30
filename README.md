# Quetzal Customer Kit

Kit privado e reproduzível para implantar o Quetzal em um workspace Databricks controlado pelo cliente. O repositório contém o App React/FastAPI, Databricks Asset Bundle, fundação Terraform, contratos de dados e runbooks operacionais.

## Princípios

- nenhum host, ID, usuário, token ou dado do ambiente de origem;
- Terraform administra a fundação; DAB administra os artefatos Databricks;
- Unity Catalog e compute serverless por padrão;
- nenhum job recorrente: bootstrap, memória, alertas e grafo são manuais;
- conectores e pesquisa externa permanecem desabilitados até aprovação explícita;
- dados reais nunca são armazenados no Git;
- produção possui `prevent_destroy` e aprovação humana.

## Início rápido

Pré-requisitos: Python 3.11+, Node.js 20+, Terraform 1.7+, Databricks CLI 0.229+ e um perfil OAuth do workspace de destino.

```bash
cp config/customer.env.example config/customer.env
cp terraform/environments/dev/dev.tfvars.example terraform/environments/dev/dev.tfvars

# Substitua todos os exemplos antes de continuar.
make preflight
make sanitize

terraform -chdir=terraform/environments/dev init
terraform -chdir=terraform/environments/dev plan -out=tfplan
terraform -chdir=terraform/environments/dev apply tfplan

make frontend-build
make bundle-validate TARGET=dev
make bundle-deploy TARGET=dev
make synthetic-data TARGET=dev
make data-contract TARGET=dev
make bootstrap TARGET=dev
make memory TARGET=dev
```

`synthetic-data` executa um único job serverless manual com duas tarefas: geração e certificação. A execução falha se volumes, schemas, chaves, regras contábeis, segurança da PII fictícia ou cobertura das jornadas da demo estiverem incorretos. Para fontes reais, não execute esse job: implemente os adapters do modo `customer`.

O grafo é intencionalmente separado e só deve ser executado quando um novo snapshot for necessário:

```bash
make graph TARGET=dev
```

## Modos de dados

- `synthetic`: fontes telecom determinísticas, sem PII real, para demonstração e testes.
- `customer`: views de adaptação implementadas pelo cliente sobre as fontes governadas existentes.

O contrato canônico está em `data_contracts/`. A implantação do App não concede acesso automático a fontes do cliente.

## Ordem de leitura

1. [Visão geral](docs/00-overview.md)
2. [Pré-requisitos](docs/01-prerequisites.md)
3. [Terraform](docs/02-terraform.md)
4. [Deploy com DAB](docs/03-dab-deploy.md)
5. [Bootstrap](docs/04-bootstrap.md)
6. [Validação](docs/05-validation.md)
7. [Operação](docs/06-operations.md)
8. [Segurança](docs/07-security.md)
9. [Roteiro de capturas](docs/screenshots/README.md)

## Componentes

```text
Terraform foundation
  └─ grupos, catálogo/schema, grants e SQL Warehouse

Databricks Asset Bundle
  ├─ Databricks App
  ├─ AI/BI Dashboard
  ├─ Genie Spaces
  ├─ Lakebase database binding
  └─ jobs manuais

Quetzal App
  ├─ React + TypeScript
  ├─ FastAPI
  ├─ Unity Catalog / Databricks SQL
  ├─ Unity AI Gateway
  ├─ Lakebase + Managed Agent Memory
  └─ OntoBricks contract
```

## Suporte

Abra uma issue privada com o resultado de `make sanitize`, `make bundle-validate` e o identificador da execução com falha. Nunca inclua tokens, PII ou arquivos de state.
