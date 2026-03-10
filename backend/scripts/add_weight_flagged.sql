-- Add weight_flagged column to pets table.
-- True when AI flagged weight as unusual for breed/age and user confirmed anyway.
-- Displayed in red on the dashboard.
ALTER TABLE pets ADD COLUMN IF NOT EXISTS weight_flagged BOOLEAN DEFAULT FALSE;
