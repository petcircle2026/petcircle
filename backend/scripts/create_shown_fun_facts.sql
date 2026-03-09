-- Migration: Create shown_fun_facts table
-- Tracks which fun facts each user has already seen to avoid repeats.

CREATE TABLE IF NOT EXISTS shown_fun_facts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    fact_hash VARCHAR(64) NOT NULL,  -- SHA-256 of the fact text
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Unique index prevents the same fact from being recorded twice for a user.
CREATE UNIQUE INDEX IF NOT EXISTS uq_shown_fun_facts_user_hash
    ON shown_fun_facts (user_id, fact_hash);

-- Index for fast lookup of all facts shown to a specific user.
CREATE INDEX IF NOT EXISTS ix_shown_fun_facts_user_id
    ON shown_fun_facts (user_id);
