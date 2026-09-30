PYTHON ?= python3
TARGET ?= dev

.PHONY: sanitize render preflight test frontend-build bundle-validate bundle-deploy data-contract bootstrap memory alerts graph

sanitize:
	$(PYTHON) scripts/sanitize_check.py

render:
	$(PYTHON) scripts/render_assets.py

preflight:
	$(PYTHON) scripts/preflight.py

test:
	$(PYTHON) -m pytest -q

frontend-build:
	cd frontend && npm ci && npm run build

bundle-validate: render
	./scripts/bundle.sh validate -t $(TARGET)

bundle-deploy: sanitize frontend-build render
	./scripts/bundle.sh deploy -t $(TARGET)

data-contract:
	./scripts/bundle.sh run -t $(TARGET) quetzal_validate_data_contract

bootstrap:
	./scripts/bundle.sh run -t $(TARGET) quetzal_operational_bootstrap

memory:
	./scripts/bundle.sh run -t $(TARGET) quetzal_memory_foundation

alerts:
	./scripts/bundle.sh run -t $(TARGET) quetzal_alert_evaluator

graph:
	./scripts/bundle.sh run -t $(TARGET) quetzal_graph_intelligence
