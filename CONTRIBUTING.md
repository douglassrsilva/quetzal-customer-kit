# Contribuir

Realice los cambios mediante pull requests. Nunca incluya identificadores del cliente, credenciales, state de Terraform, archivos de entorno locales ni capturas de producción.

Antes de abrir un pull request:

```bash
make sanitize
python -m pytest -q
ruff check app.py server tests scripts
make frontend-build
terraform -chdir=terraform/environments/dev fmt -check -recursive
terraform -chdir=terraform/environments/dev validate
```

Cuando cambie las dependencias de producción de Python, edite `requirements.in` y vuelva a generar el lock completo del despliegue:

```bash
uv pip compile requirements.in -o requirements.txt --no-emit-index-url
```

Cuando cambie exportaciones del dashboard o de Genie, ejecute `python scripts/normalize_serialized_ids.py` antes de la revisión. Los jobs costosos, la investigación externa y los conectores de salida requieren una revisión explícita de seguridad y costo.
