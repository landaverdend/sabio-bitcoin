#!/usr/bin/env bash
# Run backend, frontend, and the ADK web UI together, with each line tagged
# by source. Ctrl+C stops all three -- the trap kills the whole process
# group rather than requiring three separate Ctrl+C's in three terminals.
set -euo pipefail
cd "$(dirname "$0")/.."

export PYTHONWARNINGS=ignore:[EXPERIMENTAL]

trap 'kill 0' EXIT

run() {
  local color=$1 name=$2
  shift 2
  "$@" 2>&1 | sed -u "s/^/$(printf '\033[%sm[%s]\033[0m ' "$color" "$name")/" &
}

run 34 backend  uvicorn backend.main:app --reload --port 8010
run 35 frontend npm run dev --prefix frontend
run 36 agents   adk web agents

wait
