#!/usr/bin/env python3
"""
xlsx_to_db.py — Import Club_Gear_DB.xlsx → PostgreSQL items table.

Usage:
    python scripts/xlsx_to_db.py Club_Gear_DB.xlsx
    python scripts/xlsx_to_db.py Club_Gear_DB.xlsx --dry-run
    python scripts/xlsx_to_db.py Club_Gear_DB.xlsx --clear   # wipe items first

Reads DATABASE_URL from environment or .env file.
Sheet must have columns matching the 'items' sheet from Club_Gear_DB.xlsx:
    tag, name, description, locker, status, available,
    manufactured_date, condition_notes, borrowed_by
"""

from psycopg2.extras import execute_values
import psycopg2
import sys
import os
import argparse
import pandas as pd
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../backend/.env"))


SHEET = "items"

COLUMNS = [
    "tag",
    "name",
    "description",
    "locker",
    "status",
    "available",
    "manufactured_date",
    "condition_notes",
    "borrowed_by_email",  # sheet column is "borrowed_by", mapped below
]

VALID_STATUSES = {"active", "retired", "missing"}
VALID_LOCKERS = {"outdoor", "top", "bottom", "pad", ""}


def parse_bool(val) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().upper() == "TRUE"
    return bool(val)


def clean_row(row) -> dict | None:
    tag = str(row.get("tag", "")).strip()
    name = str(row.get("name", "")).strip()
    if not name or name.lower() in ("nan", "none", ""):
        return None

    status = str(row.get("status", "active")).strip().lower()
    if status not in VALID_STATUSES:
        status = "active"

    locker = str(row.get("locker", "")).strip().lower()
    if locker not in VALID_LOCKERS:
        locker = ""

    available = parse_bool(row.get("available", True))
    # Force unavailable if retired or missing
    if status in ("retired", "missing"):
        available = False

    borrowed_by = str(row.get("borrowed_by", "")).strip()
    if borrowed_by.lower() in ("nan", "none", ""):
        borrowed_by = None

    return {
        "tag": tag if tag and tag.lower() not in ("nan", "none") else None,
        "name": name,
        "description": str(row.get("description", "")).strip() or None,
        "locker": locker or None,
        "status": status,
        "available": available,
        "manufactured_date": str(row.get("manufactured_date", "")).strip() or None,
        "condition_notes": str(row.get("condition_notes", "")).strip() or None,
        "borrowed_by_email": borrowed_by,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("xlsx", help="Path to Club_Gear_DB.xlsx")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--clear", action="store_true",
                        help="Delete all items before import")
    args = parser.parse_args()

    db_url = os.getenv(
        "DATABASE_URL", "postgresql://gearuser:gearpass@localhost/gear")

    print(f"Reading {args.xlsx} …")
    df = pd.read_excel(args.xlsx, sheet_name=SHEET, dtype=str)
    # Rename borrowed_by → borrowed_by_email to match DB
    df = df.rename(columns={"borrowed_by": "borrowed_by_email"})
    df = df.where(pd.notna(df), None)

    rows = []
    skipped = 0
    for _, r in df.iterrows():
        cleaned = clean_row(r)
        if cleaned:
            rows.append(cleaned)
        else:
            skipped += 1

    print(f"  {len(rows)} rows to import, {skipped} skipped")

    if args.dry_run:
        for r in rows[:5]:
            print(" ", r)
        print("  (dry run — nothing written)")
        return

    conn = psycopg2.connect(db_url)
    cur = conn.cursor()

    if args.clear:
        cur.execute("DELETE FROM items")
        print(f"  Cleared items table")

    sql = """
        INSERT INTO items
            (tag, name, description, locker, status, available,
             manufactured_date, condition_notes, borrowed_by_email, created_at, updated_at)
        VALUES %s
        ON CONFLICT DO NOTHING
    """
    from datetime import datetime
    now = datetime.utcnow()
    values = [
        (
            r["tag"], r["name"], r["description"], r["locker"], r["status"],
            r["available"], r["manufactured_date"], r["condition_notes"],
            r["borrowed_by_email"], now, now
        )
        for r in rows
    ]

    execute_values(cur, sql, values)
    conn.commit()
    print(f"  Inserted {cur.rowcount} rows")
    cur.close()
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
