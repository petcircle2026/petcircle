-- Migration: Add circle column and new preventive items
-- Run this on existing production databases that already have preventive_master seeded.
--
-- Changes:
--   1. Adds 'circle' column (health/nutrition/hygiene) to preventive_master
--   2. Updates existing rows with their circle assignment
--   3. Inserts 7 new preventive items (Chronic Care, Food Ordering,
--      Nutrition Planning, Supplements, Bath & Grooming, Nail Trimming,
--      Ear Cleaning) — 14 rows total (dog + cat each)

-- Step 1: Add the circle column with a default of 'health'
ALTER TABLE preventive_master
  ADD COLUMN IF NOT EXISTS circle VARCHAR(20) NOT NULL DEFAULT 'health';

-- Step 2: Update existing items with correct circle assignments
-- Health circle: Rabies Vaccine, Core Vaccine, Feline Core, Deworming,
--               Annual Checkup, Preventive Blood Test — already default 'health'

-- Hygiene circle: Tick/Flea, Dental Check
UPDATE preventive_master SET circle = 'hygiene' WHERE item_name = 'Tick/Flea';
UPDATE preventive_master SET circle = 'hygiene' WHERE item_name = 'Dental Check';

-- Step 3: Insert new items (skip if they already exist via ON CONFLICT)

-- Chronic Care (health circle)
INSERT INTO preventive_master (id, item_name, category, circle, species, recurrence_days, medicine_dependent, reminder_before_days, overdue_after_days)
VALUES (gen_random_uuid(), 'Chronic Care', 'complete', 'health', 'dog', 180, false, 14, 14)
ON CONFLICT (item_name, species) DO NOTHING;

INSERT INTO preventive_master (id, item_name, category, circle, species, recurrence_days, medicine_dependent, reminder_before_days, overdue_after_days)
VALUES (gen_random_uuid(), 'Chronic Care', 'complete', 'health', 'cat', 180, false, 14, 14)
ON CONFLICT (item_name, species) DO NOTHING;

-- Food Ordering (nutrition circle)
INSERT INTO preventive_master (id, item_name, category, circle, species, recurrence_days, medicine_dependent, reminder_before_days, overdue_after_days)
VALUES (gen_random_uuid(), 'Food Ordering', 'complete', 'nutrition', 'dog', 30, false, 5, 3)
ON CONFLICT (item_name, species) DO NOTHING;

INSERT INTO preventive_master (id, item_name, category, circle, species, recurrence_days, medicine_dependent, reminder_before_days, overdue_after_days)
VALUES (gen_random_uuid(), 'Food Ordering', 'complete', 'nutrition', 'cat', 30, false, 5, 3)
ON CONFLICT (item_name, species) DO NOTHING;

-- Nutrition Planning (nutrition circle)
INSERT INTO preventive_master (id, item_name, category, circle, species, recurrence_days, medicine_dependent, reminder_before_days, overdue_after_days)
VALUES (gen_random_uuid(), 'Nutrition Planning', 'complete', 'nutrition', 'dog', 180, false, 14, 14)
ON CONFLICT (item_name, species) DO NOTHING;

INSERT INTO preventive_master (id, item_name, category, circle, species, recurrence_days, medicine_dependent, reminder_before_days, overdue_after_days)
VALUES (gen_random_uuid(), 'Nutrition Planning', 'complete', 'nutrition', 'cat', 180, false, 14, 14)
ON CONFLICT (item_name, species) DO NOTHING;

-- Supplements (nutrition circle)
INSERT INTO preventive_master (id, item_name, category, circle, species, recurrence_days, medicine_dependent, reminder_before_days, overdue_after_days)
VALUES (gen_random_uuid(), 'Supplements', 'complete', 'nutrition', 'dog', 30, true, 5, 3)
ON CONFLICT (item_name, species) DO NOTHING;

INSERT INTO preventive_master (id, item_name, category, circle, species, recurrence_days, medicine_dependent, reminder_before_days, overdue_after_days)
VALUES (gen_random_uuid(), 'Supplements', 'complete', 'nutrition', 'cat', 30, true, 5, 3)
ON CONFLICT (item_name, species) DO NOTHING;

-- Bath & Grooming (hygiene circle)
INSERT INTO preventive_master (id, item_name, category, circle, species, recurrence_days, medicine_dependent, reminder_before_days, overdue_after_days)
VALUES (gen_random_uuid(), 'Bath & Grooming', 'complete', 'hygiene', 'dog', 14, false, 3, 3)
ON CONFLICT (item_name, species) DO NOTHING;

INSERT INTO preventive_master (id, item_name, category, circle, species, recurrence_days, medicine_dependent, reminder_before_days, overdue_after_days)
VALUES (gen_random_uuid(), 'Bath & Grooming', 'complete', 'hygiene', 'cat', 14, false, 3, 3)
ON CONFLICT (item_name, species) DO NOTHING;

-- Nail Trimming (hygiene circle)
INSERT INTO preventive_master (id, item_name, category, circle, species, recurrence_days, medicine_dependent, reminder_before_days, overdue_after_days)
VALUES (gen_random_uuid(), 'Nail Trimming', 'complete', 'hygiene', 'dog', 21, false, 3, 7)
ON CONFLICT (item_name, species) DO NOTHING;

INSERT INTO preventive_master (id, item_name, category, circle, species, recurrence_days, medicine_dependent, reminder_before_days, overdue_after_days)
VALUES (gen_random_uuid(), 'Nail Trimming', 'complete', 'hygiene', 'cat', 21, false, 3, 7)
ON CONFLICT (item_name, species) DO NOTHING;

-- Ear Cleaning (hygiene circle)
INSERT INTO preventive_master (id, item_name, category, circle, species, recurrence_days, medicine_dependent, reminder_before_days, overdue_after_days)
VALUES (gen_random_uuid(), 'Ear Cleaning', 'complete', 'hygiene', 'dog', 14, false, 3, 3)
ON CONFLICT (item_name, species) DO NOTHING;

INSERT INTO preventive_master (id, item_name, category, circle, species, recurrence_days, medicine_dependent, reminder_before_days, overdue_after_days)
VALUES (gen_random_uuid(), 'Ear Cleaning', 'complete', 'hygiene', 'cat', 14, false, 3, 3)
ON CONFLICT (item_name, species) DO NOTHING;
