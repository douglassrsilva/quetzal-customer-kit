# Visão geral

O Quetzal conecta operações de rede, impacto no cliente, receita, churn e decisões humanas. A separação de ownership é deliberada:

| Camada | Dono | Ferramenta |
|---|---|---|
| Identidade, catálogo, schema, grants e Warehouse | Plataforma do cliente | Terraform |
| App, jobs, Genie e AI/BI | Produto Quetzal | DAB |
| Tokens, webhooks e credenciais | Segurança do cliente | Secret manager |
| Dados e políticas de acesso | Data owners do cliente | Unity Catalog |

O mesmo recurso nunca deve ser gerenciado simultaneamente por Terraform e DAB. Lakebase project/branch/endpoint são pré-requisitos; o database binding do App permanece no bundle.

## Ambientes

- `dev`: desenvolvimento isolado por usuário.
- `staging`: validação integrada e evidências de aceite.
- `prod`: promoção aprovada, sem execução automática de jobs caros.

Cada ambiente usa state Terraform, identidade, App e configuração próprios.
