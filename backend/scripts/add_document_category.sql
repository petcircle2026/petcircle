-- Migration: Add document_category column to documents table
-- Run this against your Supabase PostgreSQL database.
-- This column stores the GPT-classified document category:
--   Vaccination, Prescription, Diagnostic, Other.

ALTER TABLE documents
ADD COLUMN IF NOT EXISTS document_category VARCHAR(30) DEFAULT NULL;

-- Optional: add a check constraint to enforce valid values.
ALTER TABLE documents
ADD CONSTRAINT chk_document_category
CHECK (document_category IS NULL OR document_category IN ('Vaccination', 'Prescription', 'Diagnostic', 'Other'));
