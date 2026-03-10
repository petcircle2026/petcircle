-- Migration: Add dashboard medical tracking fields/tables
-- Run this against your Supabase PostgreSQL database.
--
-- Covers requested data foundations for:
--   1) Doctor and hospital capture from prescriptions/vaccinations
--   2) Blood/urine test value tracking + trends
--   3) Medicines tracker with add/edit/remove support

BEGIN;

-- ---------------------------------------------------------------------------
-- 1) Extend documents metadata with doctor + hospital context
-- ---------------------------------------------------------------------------
ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS doctor_name VARCHAR(200) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS hospital_name VARCHAR(200) DEFAULT NULL;

COMMENT ON COLUMN documents.doctor_name IS
  'Doctor/vet name extracted from prescription/vaccination documents.';

COMMENT ON COLUMN documents.hospital_name IS
  'Hospital/clinic name extracted from prescription/vaccination documents.';

CREATE INDEX IF NOT EXISTS idx_documents_doctor_name
  ON documents (doctor_name)
  WHERE doctor_name IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_documents_hospital_name
  ON documents (hospital_name)
  WHERE hospital_name IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 2) Medicines table (dashboard CRUD)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS prescribed_medicines (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  pet_id UUID NOT NULL REFERENCES pets(id) ON DELETE CASCADE,
  document_id UUID NULL REFERENCES documents(id) ON DELETE SET NULL,

  medicine_name VARCHAR(200) NOT NULL,
  dosage VARCHAR(200) NULL,
  frequency VARCHAR(200) NULL,
  duration VARCHAR(200) NULL,
  notes TEXT NULL,

  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  start_date DATE NULL,
  end_date DATE NULL,

  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_prescribed_medicines_pet
  ON prescribed_medicines (pet_id);

CREATE INDEX IF NOT EXISTS idx_prescribed_medicines_active
  ON prescribed_medicines (pet_id, is_active);

-- Helpful dedupe constraint for extraction retries while allowing manual edits.
CREATE UNIQUE INDEX IF NOT EXISTS uq_prescribed_medicines_doc_medicine
  ON prescribed_medicines (pet_id, document_id, medicine_name)
  WHERE document_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 3) Blood + urine diagnostic values table (for trends dashboard)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS diagnostic_test_results (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  pet_id UUID NOT NULL REFERENCES pets(id) ON DELETE CASCADE,
  document_id UUID NULL REFERENCES documents(id) ON DELETE SET NULL,

  test_type VARCHAR(30) NOT NULL,
  parameter_name VARCHAR(120) NOT NULL,
  value_numeric NUMERIC(14,4) NULL,
  value_text VARCHAR(200) NULL,
  unit VARCHAR(60) NULL,
  reference_range VARCHAR(120) NULL,
  status_flag VARCHAR(20) NULL,
  observed_at DATE NULL,

  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

  CONSTRAINT chk_diagnostic_test_type
    CHECK (test_type IN ('blood', 'urine')),
  CONSTRAINT chk_diagnostic_status_flag
    CHECK (status_flag IS NULL OR status_flag IN ('low', 'normal', 'high', 'abnormal')),
  CONSTRAINT chk_diagnostic_value_present
    CHECK (value_numeric IS NOT NULL OR value_text IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_diagnostic_results_pet
  ON diagnostic_test_results (pet_id);

CREATE INDEX IF NOT EXISTS idx_diagnostic_results_type_date
  ON diagnostic_test_results (pet_id, test_type, observed_at);

CREATE INDEX IF NOT EXISTS idx_diagnostic_results_parameter
  ON diagnostic_test_results (pet_id, parameter_name);

-- Soft dedupe to avoid duplicate extraction inserts for same report line item.
CREATE UNIQUE INDEX IF NOT EXISTS uq_diagnostic_result_dedupe
  ON diagnostic_test_results (pet_id, document_id, test_type, parameter_name, observed_at)
  WHERE document_id IS NOT NULL;

COMMIT;
