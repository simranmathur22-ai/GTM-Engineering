"""
Local SQLite cache for company research results.
Mimics the Snowflake cache behavior in the main project,
using pure Python standard library SQLite (no cloud setup needed!).
"""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

DB_FILE = Path(__file__).parent / "research_cache.db"


def init_db():
    """Create the cache table if it doesn't already exist."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS company_research_cache (
                domain TEXT PRIMARY KEY,
                data_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


def check_cache(domain: str, ttl_days: int = 7) -> Optional[dict]:
    """Check if valid research for domain exists within TTL days."""
    init_db()
    normalized = domain.lower().strip()

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT data_json, updated_at FROM company_research_cache WHERE domain = ?",
            (normalized,)
        )
        row = cursor.fetchone()

        if not row:
            return None

        data_json, updated_at_str = row
        # Parse timestamp and check TTL
        try:
            updated_at = datetime.fromisoformat(updated_at_str)
        except ValueError:
            # Fallback for standard SQLite current_timestamp format 'YYYY-MM-DD HH:MM:SS'
            updated_at = datetime.strptime(updated_at_str, "%Y-%m-%d %H:%M:%S")

        if datetime.utcnow() - updated_at <= timedelta(days=ttl_days):
            return json.loads(data_json)

        # Expired
        return None


def save_cache(domain: str, data: dict):
    """Save or update research results in the cache."""
    init_db()
    normalized = domain.lower().strip()
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    data_json = json.dumps(data)

    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO company_research_cache (domain, data_json, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(domain) DO UPDATE SET
                data_json = excluded.data_json,
                updated_at = excluded.updated_at
        """, (normalized, data_json, now_str, now_str))
        conn.commit()


def clear_cache():
    """Clear all cached entries."""
    init_db()
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM company_research_cache")
        conn.commit()
