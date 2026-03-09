-- Migration: Add source_wamid column to documents table
-- Run this against your Supabase PostgreSQL database.
-- This column stores the WhatsApp message ID that triggered the upload,
-- preventing phantom duplicate uploads when Meta retries webhooks.

ALTER TABLE documents
ADD COLUMN IF NOT EXISTS source_wamid VARCHAR(200) DEFAULT NULL;

-- Unique index on source_wamid (partial — excludes NULLs).
-- Ensures one Document per WhatsApp message.
CREATE UNIQUE INDEX IF NOT EXISTS uq_documents_source_wamid
ON documents (source_wamid) WHERE source_wamid IS NOT NULL;
