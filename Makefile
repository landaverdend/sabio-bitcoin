.PHONY: help install db-up db-down migrate backfill backend agents comms dev

# Silence ADK's "[EXPERIMENTAL] ..." startup warnings (they flag ADK-internal
# features we don't configure); everything else still surfaces normally.
export PYTHONWARNINGS := ignore:[EXPERIMENTAL]

help:
	@echo "make install   - install python dependencies"
	@echo "make db-up     - start the postgres container"
	@echo "make db-down   - stop the postgres container"
	@echo "make migrate   - apply database migrations"
	@echo "make backfill  - download the bitcoin-dev archive and load messages + people"
	@echo "make backend   - run the backend API (foreground)"
	@echo "make agents    - run the ADK web UI with the root Sabio agent (foreground)"
	@echo "make comms     - run the ADK web UI with repos/comms individually selectable, for testing comms directly (foreground)"
	@echo "make dev       - start db and apply migrations"

install:
	pip install -r requirements.txt

db-up:
	cd db && docker compose up -d

db-down:
	cd db && docker compose down

migrate:
	python3 db/migrate.py

backfill:
	python3 scripts/backfill_mailing_list.py
	python3 scripts/backfill_satoshi_emails.py

backend:
	uvicorn backend.main:app --reload

agents:
	adk web

comms:
	adk web agents

dev: db-up migrate
	@echo "Postgres is up and migrated. Run 'make backend' and 'make agents' in separate terminals."
