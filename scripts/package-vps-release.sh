#!/bin/sh
set -eu

output=${1:-prod-vps-bundle.tar.gz}
git archive --format=tar.gz --output="$output" HEAD -- \
  .dockerignore .env.example Dockerfile docker-compose.yml init_db.py requirements.txt \
  flaskr nginx/default.conf public/output.css public/static \
  scripts/migrate_affiliate.py docs/affiliate-uzemeltetes.md \
  ':(exclude,glob)**/__pycache__/**' \
  ':(exclude,glob)flaskr/**/.env*' ':(exclude,glob)public/**/.env*' ':(exclude,glob)**/*.pyc' \
  ':(exclude,glob)**/*.db*' ':(exclude,glob)**/*.sqlite*' \
  ':(exclude,glob)**/*.backup*' ':(exclude,glob)**/*.original' \
  ':(exclude,glob)**/*.key' ':(exclude,glob)**/*.pem'
