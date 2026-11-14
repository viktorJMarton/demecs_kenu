#!/usr/bin/env bash
set -euo pipefail

target_dir=$(realpath "${1:-.}")
http_port=${DEMECS_HTTP_PORT:-8080}

sqlite3 -readonly "$target_dir/kajak_kenu.db" "PRAGMA integrity_check;" |
  grep -qx ok
test -n "$(find "$target_dir/public/uploads" -type f -print -quit)"

cd "$target_dir"
docker compose config --quiet
docker compose ps

for attempt in $(seq 1 30); do
  if curl --fail --silent --show-error "http://127.0.0.1:${http_port}/" >/dev/null; then
    echo "Application smoke test passed."
    exit 0
  fi
  sleep 2
done

echo "Application did not become ready." >&2
docker compose logs --tail=200
exit 1
