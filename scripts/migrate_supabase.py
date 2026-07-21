"""Apply the Signal Supabase schema from database/schema.sql."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from urllib.parse import quote

import psycopg
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = PROJECT_ROOT / "database" / "schema.sql"
SUCCESS_MESSAGE = "Supabase schema migration completed successfully."


def _normalize_database_url(url: str) -> str:
    """Percent-encode credentials so special characters in passwords are valid."""
    match = re.match(
        r"^(postgresql(?:\+\w+)?://)([^:@/]+):(.+)@([^/]+)(/.*)?$",
        url,
    )
    if not match:
        return url

    scheme, user, password, hostport, path = match.groups()
    encoded_password = quote(password, safe="")
    return f"{scheme}{user}:{encoded_password}@{hostport}{path or ''}"


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL is not set in .env", file=sys.stderr)
        return 1

    if not SCHEMA_PATH.is_file():
        print(f"ERROR: Schema file not found: {SCHEMA_PATH}", file=sys.stderr)
        return 1

    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    database_url = _normalize_database_url(database_url)

    try:
        with psycopg.connect(database_url) as conn:
            conn.execute(schema_sql)
            conn.commit()
    except Exception as exc:
        print(f"ERROR: Supabase schema migration failed: {exc}", file=sys.stderr)
        return 1

    print(SUCCESS_MESSAGE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
