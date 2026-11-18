# Database infrastructure
    # Creating database connections.
    # Configuring SQLite connections.
    # Initializing tables and schemas.

import sqlite3

# open connection to database
def get_connection(path):
    
    # allow python to make connection with db
    conn = sqlite3.connect(path)
    # control the format of returned rows
    conn.row_factory = sqlite3.Row
    
    return conn


# create the table if it doesnot exists
def init_db(conn):
    conn.execute("""
                 CREATE TABLE IF NOT EXISTS expenses(
                     idempotency_key TEXT UNIQUE,
                     id INTEGER PRIMARY KEY AUTOINCREMENT,
                     owner_id TEXT NOT NULL DEFAULT 'local',
                     amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
                     currency TEXT NOT NULL DEFAULT 'ETB',
                     category TEXT NOT NULL,
                     description TEXT,
                     spent_on TEXT, 
                     created_at TEXT
                 )
                 """)

    conn.execute("""
                 CREATE TABLE IF NOT EXISTS pending_deletions(
                     id  INTEGER PRIMARY KEY AUTOINCREMENT,
                     owner_id TEXT NOT NULL,
                     expense_ids TEXT,
                     status TEXT,
                     expires_at TEXT
                 )
                 """)

    # One row per session: the whole message list stored as JSON text.
    conn.execute("""
                 CREATE TABLE IF NOT EXISTS conversations(
                     owner_id TEXT PRIMARY KEY,
                     messages TEXT NOT NULL,
                     updated_at TEXT
                 )
                 """)

    
    conn.commit()
    
