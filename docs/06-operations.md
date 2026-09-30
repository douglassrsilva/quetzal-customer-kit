# Operación

## Jobs

| Job | Frecuencia | Costo esperado |
|---|---|---|
| Generación y certificación sintética | manual, preparación o reinicio de la demo | bajo a moderado |
| Bootstrap operativo | manual, instalación o cambio de esquema | bajo |
| Managed Memory Foundation | manual | bajo |
| Motor de alertas | manual desde la aplicación | bajo |
| Graph Intelligence | manual y aprobado | mayor |

Ningún job debe recibir un `schedule` o `trigger` sin un cambio revisado.

El job sintético utiliza `max_concurrent_runs=1`, falla de forma segura al encontrar tablas que no pertenecen al kit y nunca debe ejecutarse en el esquema de fuentes reales del cliente.

## Logs

```bash
databricks apps logs "$BUNDLE_VAR_app_name" --tail-lines 500 --profile "$DATABRICKS_CONFIG_PROFILE"
```

No copie payloads con PII en las issues. Utilice trace IDs, run IDs y mensajes redactados.

## Conectores y salida de red

CRM/BSS/OSS y la investigación externa comienzan deshabilitados. Habilítelos únicamente después de aprobar la lista de destinos, guardar el secreto en la bóveda del cliente y validar timeout, idempotencia y aprobación humana.
