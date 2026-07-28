# Sabio

Sabio is a research tool for Bitcoin development. It combines live GitHub data
with an indexed archive of technical discussions and contributor identities, then
links answers back to their sources.

## Features

- Chat over commits, pull requests, issues, source code, BIPs, and discussions
- Citations that open the referenced code or archived message
- Repository browsing for branches, files, blame, commits, and diffs
- Contributor search across GitHub, mailing lists, IRC, and BitcoinTalk
- Image, repository, person, file, and code-range attachments
- Nostr authentication and persistent conversations
- English and Spanish interfaces

Configured repositories:

| Alias | Repository |
| --- | --- |
| `core` | `bitcoin/bitcoin` |
| `knots` | `bitcoinknots/bitcoin` |
| `bips` | `bitcoin/bips` |
| `secp256k1` | `bitcoin-core/secp256k1` |

The archive supports bitcoin-dev and related historical mailing lists,
p2p-research, BitcoinTalk development discussions, and selected Bitcoin Core IRC
channels.

## Stack

- React, TypeScript, and Vite
- FastAPI
- Google ADK, LiteLLM, and OpenAI
- PostgreSQL
- GitHub API

## Local setup

Requirements:

- Python 3.12.11
- Node.js 22.12 or newer
- Docker with Docker Compose
- An OpenAI API key
- A NIP-07 Nostr browser extension
- A GitHub token, recommended to avoid low API rate limits

Install the project:

```bash
git clone <repository-url>
cd sabio-bitcoin

python -m venv .venv
source .venv/bin/activate
make install
make frontend-install
```

Create the local environment file:

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Set `OPENAI_API_KEY` and `SESSION_SECRET` in `.env`. The template includes the
local PostgreSQL configuration. Set `GITHUB_TOKEN` for higher GitHub API limits.

Start and migrate PostgreSQL:

```bash
make dev
```

Start the backend, frontend, and ADK development UI:

```bash
make dev-all
```

| Service | URL |
| --- | --- |
| Frontend | `http://localhost:5173` |
| Backend | `http://localhost:8010` |
| ADK web UI | `http://localhost:8000` |

The services can also be started separately:

```bash
make backend
make frontend
make agents
```

Run `make help` for the full command list.

## Load archive data

GitHub browsing works without a local archive. Communication search and the people
directory require data in PostgreSQL.

```bash
# Mailing lists and early archives
make backfill

# One-time BitcoinTalk history import
make backfill-bitcointalk-history

# Recent BitcoinTalk posts
make scrape-bitcointalk

# One-time IRC history import
make backfill-irc

# Link commit authors to GitHub accounts
make link-github
```

The importers are safe to resume. Incremental jobs can be run with:

```bash
python -m jobs.sync_mailing_list
python -m jobs.sync_bitcointalk
python -m jobs.sync_irc
```

## Tests

Run the Python suite:

```bash
pytest -q
```

Check and build the frontend:

```bash
cd frontend
npm run lint
npm run build
```

Run browser tests:

```bash
cd frontend
npx playwright install chromium  # first run only
npm run test:e2e
```

The browser tests use mocked APIs and do not require PostgreSQL, external APIs, a
Nostr extension, or an OpenAI key.

With the application running, test Nostr login and session persistence:

```bash
python scripts/smoke_sessions.py
```

## Production

Build and run the production image:

```bash
docker build -t sabio-bitcoin .
docker run --rm -p 8080:8080 --env-file .env sabio-bitcoin
```

The container's `DATABASE_URL` must point to a reachable PostgreSQL server. Apply
database migrations before serving traffic.

Fly.io deployment is configured in `fly.toml`:

```bash
fly secrets set \
  OPENAI_API_KEY="<key>" \
  SESSION_SECRET="<secret>" \
  DATABASE_URL="<postgres-url>" \
  GITHUB_TOKEN="<token>"

fly deploy
```

## Project layout

```text
agents/       Agent coordinator, specialists, and tools
backend/      FastAPI application
db/           PostgreSQL helpers, Compose config, and migrations
frontend/     React application
jobs/         Incremental synchronization jobs
scripts/      Backfills, identity maintenance, and smoke tests
tests/        Backend, agent, ingestion, and resolution tests
```
