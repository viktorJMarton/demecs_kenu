#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "Usage: $0 BUNDLE_DIR TARGET_DIR PASSPHRASE_FILE" >&2
  exit 2
fi

bundle_dir=$(realpath "$1")
target_dir=$(realpath -m "$2")
passphrase_file=$(realpath "$3")

for command in docker openssl sha256sum sqlite3 tar; do
  command -v "$command" >/dev/null || {
    echo "Missing required command: $command" >&2
    exit 1
  }
done

test -f "$bundle_dir/SHA256SUMS"
test -f "$bundle_dir/images/docker-images.tar.gz"
test -f "$bundle_dir/state/state.tar.gz.enc"
test -d "$bundle_dir/source"
test -f "$passphrase_file"

(cd "$bundle_dir" && sha256sum -c SHA256SUMS)

mkdir -p "$target_dir"
cp -a "$bundle_dir/source/." "$target_dir/"

state_archive=$(mktemp)
trap 'rm -f "$state_archive"' EXIT
openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 \
  -pass "file:$passphrase_file" \
  -in "$bundle_dir/state/state.tar.gz.enc" \
  -out "$state_archive"
tar -xzf "$state_archive" -C "$target_dir"

chmod 600 "$target_dir/.env.runtime" "$target_dir/kajak_kenu.db"
mkdir -p "$target_dir/logs"

sqlite3 -readonly "$target_dir/kajak_kenu.db" "PRAGMA integrity_check;"
sqlite3 -readonly "$target_dir/kajak_kenu.db" "PRAGMA foreign_key_check;"

docker load -i "$bundle_dir/images/docker-images.tar.gz"
(cd "$target_dir" && docker compose up -d --no-build)

echo "Restore started. Run deploy/verify_restored_stack.sh $target_dir."
