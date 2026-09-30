# Quetzal + OntoBricks

El contrato de integración es la tabla de Unity Catalog `gold_quetzal_knowledge_graph_triples`. Las tres primeras columnas siguen el contrato nativo de OntoBricks (`subject`, `predicate`, `object`); las demás conservan el tipo de objeto, linaje, ejecución y fecha de generación.

Ejecute `make render` e importe `build/generated/ontology/quetzal-telecom-v1.ttl` como ontología del dominio `quetzal-telecom`. A continuación, dirija la sincronización Lakehouse a la tabla de triples. El snapshot se genera únicamente mediante el job manual DAB `quetzal_graph_intelligence`.

La analítica genérica de OntoBricks convierte las relaciones en un grafo no dirigido y sin pesos. Para churn, Quetzal conserva los algoritmos ponderados en su propio pipeline y utiliza OntoBricks para semántica, navegación, validación y GraphQL/MCP. De esta forma no se descartan la frecuencia, la duración, la recencia ni la reciprocidad.
