.PHONY: infra infra-down agent execution artifact runtime seed install

install:
	pip install -e ".[dev]"

infra:
	docker compose up -d

infra-down:
	docker compose down

agent:
	PYTHONPATH=. uvicorn services.agent.app:app --port 8000 --reload

execution:
	PYTHONPATH=. uvicorn services.execution.app:app --port 8001 --reload

artifact:
	PYTHONPATH=. uvicorn services.artifact.app:app --port 8002 --reload

runtime-sql:
	PYTHONPATH=. uvicorn services.sql_runtime.app:app --port 8010 --reload

seed:
	PYTHONPATH=. python3 scripts/seed.py

all-services:
	@echo "Run each in a separate terminal:"
	@echo "  make artifact"
	@echo "  make runtime-sql"
	@echo "  make execution"
	@echo "  make agent"
