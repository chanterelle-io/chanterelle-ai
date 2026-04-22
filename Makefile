.PHONY: infra infra-down agent execution artifact runtime-sql runtime-python seed install

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

runtime-python:
	PYTHONPATH=. uvicorn services.python_runtime.app:app --port 8011 --reload

seed:
	PYTHONPATH=. python3 scripts/seed.py

migrate-phase2:
	PYTHONPATH=. python3 scripts/migrate_phase2.py

migrate-phase3:
	PYTHONPATH=. python3 scripts/migrate_phase3.py

migrate-phase4:
	PYTHONPATH=. python3 scripts/migrate_phase4.py

migrate-phase5:
	PYTHONPATH=. python3 scripts/migrate_phase5.py

all-services:
	@echo "Run each in a separate terminal:"
	@echo "  make artifact"
	@echo "  make runtime-sql"
	@echo "  make runtime-python"
	@echo "  make execution"
	@echo "  make agent"
