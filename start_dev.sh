#!/usr/bin/env bash
# start_dev.sh - start tmux dev session, autodetects user shell for pane commands
set -e

SESSION="dev"

# Detect the user's shell (fish, bash, zsh, etc.)
USER_SHELL="${SHELL:-/bin/bash}"
SHELL_NAME="$(basename "$USER_SHELL")"

# Build the uvicorn command — no activation needed, use venv directly
UVICORN_CMD=".venv/bin/uvicorn main:app --reload --reload-include '.env'"

# Wrap command for fish (uses `; and` chaining and different source syntax)
if [ "$SHELL_NAME" = "fish" ]; then
  UVICORN_CMD="source .venv/bin/activate.fish; and $UVICORN_CMD"
else
  UVICORN_CMD="source .venv/bin/activate && $UVICORN_CMD"
fi

# Create tmux session if it doesn't exist
if ! tmux has-session -t "$SESSION" 2>/dev/null; then
  # Start detached session, opening panes with the user's shell
  tmux new-session -d -s "$SESSION" -n "services" -x "$(tput cols)" -y "$(tput lines)"

  # Pane 0: spare / docker compose
  # tmux send-keys -t "$SESSION":0.0 'docker compose up' C-m

  # Pane 1 (right): Uvicorn
  tmux split-window -h -t "$SESSION":0
  tmux send-keys -t "$SESSION":0.1 "$UVICORN_CMD" C-m

  # Focus left pane
  tmux select-pane -t "$SESSION":0.0
fi

# Attach to the session
tmux attach -t "$SESSION"

# After tmux exits — unset .env vars in this shell process
# Note: only affects the current subshell, not the parent terminal.
# To unset in your shell session, source this script instead of executing it.
if [ -f .env ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    # Skip comments and empty lines
    [[ "$line" =~ ^\s*# ]] && continue
    [[ -z "$line" ]] && continue
    VAR="${line%%=*}"
    unset "$VAR"
  done < .env
fi
