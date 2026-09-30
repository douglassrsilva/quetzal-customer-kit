# Evidências e capturas

Todas as capturas devem ser produzidas em `staging` com dados sintéticos. Oculte barra do navegador, e-mail, hostname, workspace ID, run URL, principal IDs, Lakebase host e PII.

| Arquivo | Evidência |
|---|---|
| `01-repository-private.png` | visibilidade privada e branch protection |
| `02-auth-profile.png` | autenticação válida, sem token |
| `03-sanitize-pass.png` | scanner aprovado |
| `04-terraform-plan.png` | resumo do plan sem valores sensíveis |
| `05-terraform-apply.png` | apply concluído |
| `06-foundation-resources.png` | catálogo, schema e Warehouse |
| `07-bundle-validate.png` | bundle validado |
| `08-bundle-deploy.png` | deploy concluído |
| `09-bootstrap-run.png` | bootstrap manual bem-sucedido |
| `10-app-running.png` | App em RUNNING |
| `11-preflight.png` | preflight do Quetzal |
| `12-genie.png` | nova conversa e resposta com gráfico |
| `13-quetzal-iq.png` | conversa com memória e fontes |
| `14-dashboard.png` | AI/BI incorporado |
| `15-customer-360.png` | Cliente 360 fictício |
| `16-graph-manual.png` | grafo e botão de refresh manual |
| `17-voc-campaigns.png` | Voz do Cliente e campanha em DRAFT |
| `18-logs.png` | logs redigidos e troubleshooting |

Use a persona fictícia `Ana Exemplo`, cliente `CUS-DEMO-0001`, catálogo `acme_telco` e domínio `example.com`. Antes do commit, execute `make sanitize` e faça revisão visual independente.
