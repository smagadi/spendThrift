.PHONY: run init-db test

run:
	./scripts/run_app.sh

init-db:
	.venv/bin/python scripts/init_db.py

test:
	.venv/bin/pytest -q
