CREATE TABLE IF NOT EXISTS customers (
  id TEXT PRIMARY KEY,
  email TEXT,
  plan TEXT,
  cloud INTEGER,
  license TEXT,
  session_id TEXT
);
CREATE INDEX IF NOT EXISTS customers_session ON customers (session_id);
CREATE TABLE IF NOT EXISTS devices (
  id TEXT PRIMARY KEY,
  customer TEXT,
  kind TEXT,
  revoked INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  action TEXT,
  customer TEXT,
  at TEXT
);
CREATE TABLE IF NOT EXISTS flags (
  name TEXT PRIMARY KEY,
  enabled INTEGER DEFAULT 0
);
