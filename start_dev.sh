#!/usr/bin/env bash
# start.sh - start tmux session and unset .env vars on exit
set -e

# Load env var names from .env (skip comments)
ENV_VARS=$(grep -v '^\s*#' .env | sed -E 's/=.*//')

SESSION="dev"

# Create tmux session if it doesn't exist
if ! tmux has-session -t "$SESSION" 2>/dev/null; then
  # Start a detached session named "dev",
  tmux new-session -d -s "$SESSION" -n "services"

  # Pane 0: Docker Compose
  tmux send-keys -t "$SESSION":0.0 'docker compose rm && docker compose up' C-m

  # Split vertically for Uvicorn in pane 1
  tmux split-window -h -t "$SESSION":0
  tmux send-keys -t "$SESSION":0.1 'pipenv run uvicorn main:app --reload --reload-include ".env"' C-m
fi

# Attach to the tmux session
tmux attach -t "$SESSION"

# After tmux session ends, unset all loaded .env variables
for VAR in $ENV_VARS; do
  unset "$VAR"
done
