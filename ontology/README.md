# Quetzal + OntoBricks

O contrato de integração é a tabela Unity Catalog
`gold_quetzal_knowledge_graph_triples`. As três primeiras colunas seguem o
contrato nativo do OntoBricks (`subject`, `predicate`, `object`); as demais
preservam tipo do objeto, linhagem, execução e data de geração.

Execute `make render` e importe `build/generated/ontology/quetzal-telecom-v1.ttl`
como ontologia do domínio `quetzal-telecom`. Em seguida,
aponte a sincronização Lakehouse para a tabela de triplas. O snapshot é gerado
somente pelo job manual DAB `quetzal_graph_intelligence`.

O analytics genérico do OntoBricks converte relações em um grafo não direcionado
e sem pesos. Para churn, o Quetzal mantém os algoritmos ponderados no pipeline
próprio e usa o OntoBricks para semântica, navegação, validação e GraphQL/MCP.
Isso evita descartar frequência, duração, recência e reciprocidade.
