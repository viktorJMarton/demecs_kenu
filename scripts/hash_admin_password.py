"""Utility for generating an `ADMIN_USERS_JSON` entry with a known password hash."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

from werkzeug.security import generate_password_hash


DEFAULT_PASSWORD = "DeMégisAvízAzÚr"


def _format_env_lines(lines: Iterable[str], formatted_json: str) -> list[str]:
    updated = []
    replaced = False
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("ADMIN_USERS_JSON="):
            indentation = line[: len(line) - len(line.lstrip())]
            updated.append(f"{indentation}ADMIN_USERS_JSON={formatted_json}")
            replaced = True
        else:
            updated.append(line)
    if not replaced:
        updated.append(f"ADMIN_USERS_JSON={formatted_json}")
    return updated


def _update_env_file(env_path: Path, formatted_json: str) -> Path:
    contents = env_path.read_text(encoding="utf-8").splitlines()
    updated_lines = _format_env_lines(contents, formatted_json)
    env_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
    return env_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an ADMIN_USERS_JSON entry for admin login.")
    parser.add_argument("--username", default="admin", help="Username to grant admin access (default: %(default)s)")
    parser.add_argument(
        "--password",
        default=DEFAULT_PASSWORD,
        help="Plain-text password to hash (default: %(default)s)",
    )
    parser.add_argument(
        "--method",
        default="scrypt",
        help="Werkzeug hashing method to use (default: %(default)s)",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        help="Optional path to an env file to update with the new ADMIN_USERS_JSON line.",
    )

    args = parser.parse_args()
    password_hash = generate_password_hash(args.password, method=args.method)
    entry = [{"username": args.username, "password_hash": password_hash}]
    formatted = json.dumps(entry, ensure_ascii=False)

    print("Use the following entry for ADMIN_USERS_JSON:")
    print(formatted)

    if args.env_file:
        env_path = args.env_file
        if not env_path.exists():
            raise FileNotFoundError(f"Env file not found: {env_path}")
        updated_path = _update_env_file(env_path, formatted)
        print(f"Updated {updated_path.resolve()}")


if __name__ == "__main__":
    main()
