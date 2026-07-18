.PHONY: help install frontend-install db-up db-down migrate backfill link-github scrape-bitcointalk backfill-bitcointalk-history backend agents frontend dev dev-all

# Silence ADK's "[EXPERIMENTAL] ..." startup warnings (they flag ADK-internal
# features we don't configure); everything else still surfaces normally.
export PYTHONWARNINGS := ignore:[EXPERIMENTAL]

help:
	@echo "make install           - install python dependencies"
	@echo "make db-up             - start the postgres container"
	@echo "make db-down           - stop the postgres container"
	@echo "make migrate           - apply database migrations"
	@echo "make backfill          - download the bitcoin-dev archive and load messages + people"
	@echo "make link-github       - link people to GitHub accounts (~30 min, ~1300 API calls)"
	@echo "make scrape-bitcointalk - ongoing BitcoinTalk crawl, recency-sorted (cron-friendly, catches new posts cheaply)"
	@echo "make backfill-bitcointalk-history - ONE-TIME full-history BitcoinTalk backfill, oldest topic first (slow discovery pass)"
	@echo "make backend           - run the backend API (foreground)"
	@echo "make agents            - run the ADK web UI (foreground)"
	@echo "make frontend          - run the frontend dev server (foreground)"
	@echo "make dev               - start db and apply migrations"
	@echo "make dev-all           - run backend + frontend + agents together (foreground, Ctrl+C stops all)"

install:
	pip install -r requirements.txt

frontend-install:
	cd frontend && npm install

db-up:
	cd db && docker compose up -d

db-down:
	cd db && docker compose down

migrate:
	python3 db/migrate.py

backfill:
	python3 scripts/backfill_mailing_list.py
	python3 scripts/backfill_early_archives.py

link-github:
	python3 scripts/link_github_contributors.py

scrape-bitcointalk:
	python3 scripts/scrape_bitcointalk.py

backfill-bitcointalk-history:
	python3 scripts/backfill_bitcointalk_history.py

# 8010, not uvicorn's default 8000 -- `adk web` also defaults to 8000, and
# `make dev-all` runs both backend and agents at once.
backend:
	uvicorn backend.main:app --reload --port 8010

agents:
	adk web agents

frontend:
	cd frontend && npm run dev

dev: db-up migrate
	@echo "Postgres is up and migrated. Run 'make backend' and 'make agents' in separate terminals."

dev-all:
	./scripts/dev.sh
