-- Add doc_upload_deadline column for post-onboarding upload window.
-- Nullable TIMESTAMPTZ; set when user enters awaiting_documents state,
-- cleared when they transition to complete.
ALTER TABLE users ADD COLUMN IF NOT EXISTS doc_upload_deadline TIMESTAMPTZ;
