.PHONY: dev test migrate downgrade revision openapi codegen-hint lint seed

# Run the dev server on SQLite (zero external services).
dev:
	uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Run the test suite.
test:
	uv run pytest

# Apply migrations to head (creates the SQLite db if absent).
migrate:
	uv run alembic upgrade head

downgrade:
	uv run alembic downgrade -1

# Autogenerate a new migration: make revision m="message"
revision:
	uv run alembic revision --autogenerate -m "$(m)"

# Dump the published client contract to openapi.json (admin routes excluded).
openapi:
	uv run python scripts/export_openapi.py

# Print the client-side TypeScript codegen command.
codegen-hint:
	@echo "Client codegen (run in the game-client repo):"
	@echo "  npx openapi-typescript ./openapi.json -o src/net/embassy-types.ts"

# Insert a small synthetic corpus for poking at the admin UI.
seed:
	uv run python scripts/seed_demo.py

lint:
	uv run ruff check app tests scripts
