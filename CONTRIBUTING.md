# Contributing

Create changes through pull requests. Never commit customer identifiers, credentials, Terraform state, local environment files or production screenshots.

Before opening a pull request:

```bash
make sanitize
python -m pytest -q
ruff check app.py server tests scripts
make frontend-build
terraform -chdir=terraform/environments/dev fmt -check -recursive
terraform -chdir=terraform/environments/dev validate
```

When changing Python production dependencies, edit `requirements.in` and regenerate the complete deployment lock:

```bash
uv pip compile requirements.in -o requirements.txt --no-emit-index-url
```

When changing dashboard or Genie exports, run `python scripts/normalize_serialized_ids.py` before review. Expensive jobs, external research and outbound connectors require an explicit security and cost review.
