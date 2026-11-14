# Docker VPS migration

The production stack consists of the application container and an internal
Nginx container. Persistent state is deliberately outside the image:

- `kajak_kenu.db` -> `/app/kajak_kenu.db`
- `public/uploads` -> `/app/public/uploads`
- `.env.runtime` -> `/app/.env` using Compose `format: raw`
- `logs` -> `/app/logs`

Never commit these stateful or secret files. A migration bundle must contain
an encrypted state archive, saved Docker images, checksums, restore scripts,
and a source revision matching the application image.

## Restore order

1. Install Docker Engine, Docker Compose, Nginx and Certbot.
2. Verify the outer bundle checksum and every entry in `SHA256SUMS`.
3. Decrypt and extract the state archive into the restored project directory.
4. Run `PRAGMA integrity_check` and `PRAGMA foreign_key_check`.
5. Load the saved images and start the Compose stack.
6. Install the host Nginx template, issue a new Let's Encrypt certificate,
   and point DNS to the new VPS only after local smoke tests pass.
7. Verify static files, uploads, admin login, booking preview and payment
   configuration without initiating a real charge.

The migration package generated on 2026-11-14 includes a machine-readable
manifest and an automated isolated restore test report.
