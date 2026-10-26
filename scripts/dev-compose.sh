#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

# An explicit empty interpolation file prevents Docker Compose from loading the
# repository's production .env automatically. Runtime DEV values live in the
# dedicated compose file and never reuse production credentials.
exec docker compose \
  --env-file /dev/null \
  --project-directory "$PROJECT_DIR" \
  -f "$PROJECT_DIR/docker-compose.dev.yml" \
  "$@"
