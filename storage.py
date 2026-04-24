"""SQLite-backed lead storage."""
import csv
import json
import sqlite3
from contextlib import contextmanager
from typing import Generator

import config
from models import Lead


SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name       TEXT,
    first_name      TEXT,
    last_name       TEXT,
    email           TEXT,
    phone           TEXT,
    title           TEXT,
    company         TEXT,
    company_domain  TEXT,
    linkedin_url    TEXT,
    website         TEXT,
    city            TEXT,
    state           TEXT,
    country         TEXT,
    source_actor    TEXT,
    source_dataset  TEXT,
    raw             TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_email ON leads(email) WHERE email != '';
CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_linkedin ON leads(linkedin_url) WHERE linkedin_url != '';
"""


@contextmanager
def _conn() -> Generator[sqlite3.Connection, None, None]:
    con = sqlite3.connect(config.DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db() -> None:
    with _conn() as con:
        con.executescript(SCHEMA)


def upsert_leads(leads: list[Lead]) -> tuple[int, int]:
    """Insert leads, skipping duplicates. Returns (inserted, skipped)."""
    inserted = skipped = 0
    with _conn() as con:
        for lead in leads:
            d = lead.to_dict()
            try:
                con.execute(
                    """
                    INSERT INTO leads
                        (full_name, first_name, last_name, email, phone, title,
                         company, company_domain, linkedin_url, website,
                         city, state, country, source_actor, source_dataset, raw)
                    VALUES
                        (:full_name, :first_name, :last_name, :email, :phone, :title,
                         :company, :company_domain, :linkedin_url, :website,
                         :city, :state, :country, :source_actor, :source_dataset, :raw)
                    """,
                    {**d, "raw": json.dumps(lead.raw)},
                )
                inserted += 1
            except sqlite3.IntegrityError:
                skipped += 1
    return inserted, skipped


def query_leads(
    company: str = "",
    email: str = "",
    name: str = "",
    limit: int = 500,
) -> list[dict]:
    clauses, params = [], []
    if company:
        clauses.append("company LIKE ?")
        params.append(f"%{company}%")
    if email:
        clauses.append("email LIKE ?")
        params.append(f"%{email}%")
    if name:
        clauses.append("full_name LIKE ?")
        params.append(f"%{name}%")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"SELECT * FROM leads {where} ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    with _conn() as con:
        rows = con.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def count_leads() -> int:
    with _conn() as con:
        return con.execute("SELECT COUNT(*) FROM leads").fetchone()[0]


def export_to_csv(path: str, **filters) -> int:
    rows = query_leads(**filters, limit=100_000)
    if not rows:
        return 0
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)
