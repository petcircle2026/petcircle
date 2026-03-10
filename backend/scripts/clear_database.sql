-- Clear all data from the database (keeps preventive_master reference data).
-- Truncates tables in FK-safe order (children first) using CASCADE.

TRUNCATE TABLE message_logs CASCADE;
TRUNCATE TABLE conflict_flags CASCADE;
TRUNCATE TABLE reminders CASCADE;
TRUNCATE TABLE preventive_records CASCADE;
TRUNCATE TABLE documents CASCADE;
TRUNCATE TABLE dashboard_tokens CASCADE;
TRUNCATE TABLE pets CASCADE;
TRUNCATE TABLE users CASCADE;
