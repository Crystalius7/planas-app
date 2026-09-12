-- schema.sql - D1 (SQLite). Apply: npx wrangler d1 execute planas --file=schema.sql
-- No Moodle credential, course file or study answer is stored here: blobs are client-side encrypted (the server keeps ciphertext).
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  plan TEXT NOT NULL DEFAULT 'none',          -- none | trial | paid
  trial_ends_at TEXT,
  trial_fp TEXT,                              -- hashed Moodle identity used for the trial (one signal among several)
  billing_ref TEXT,
  share_data INTEGER NOT NULL DEFAULT 0,      -- consent to share non-personal usage data (off by default)
  consent_at TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS blobs (
  user_id TEXT NOT NULL,
  name TEXT NOT NULL,
  data TEXT NOT NULL,                         -- ciphertext (AES-GCM, key derived on the device)
  updated_at TEXT NOT NULL,
  PRIMARY KEY (user_id, name)
);
CREATE TABLE IF NOT EXISTS reports (
  id TEXT PRIMARY KEY,
  user_id TEXT,
  kind TEXT NOT NULL,
  text TEXT NOT NULL,
  page TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS push (
  user_id TEXT NOT NULL,
  endpoint TEXT NOT NULL,
  data TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (user_id, endpoint)
);
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  payload TEXT NOT NULL,
  status TEXT NOT NULL,                       -- queued | leased | done | failed
  lease_until TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  result TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT
);
CREATE INDEX IF NOT EXISTS jobs_status ON jobs (status, created_at);
