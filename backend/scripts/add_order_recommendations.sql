-- PetCircle — Database Migration for Order Recommendations and Pet Preferences
-- 
-- This migration adds support for:
-- 1. AI-generated order recommendations (cached to reduce API calls)
-- 2. Pet preferences (tracks user ordering patterns for personalization)

-- Create order_recommendations table
-- Caches AI-generated recommendations for pet profiles
CREATE TABLE IF NOT EXISTS order_recommendations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pet_id UUID REFERENCES pets(id) ON DELETE CASCADE,
    species VARCHAR(10) NOT NULL,
    breed VARCHAR(100),
    age_range VARCHAR(20),
    category VARCHAR(30) NOT NULL,
    items JSONB NOT NULL DEFAULT '[]'::jsonb,
    used_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes for recommendations lookup
CREATE INDEX IF NOT EXISTS ix_order_recommendations_species 
    ON order_recommendations(species);
CREATE INDEX IF NOT EXISTS ix_order_recommendations_breed 
    ON order_recommendations(breed);
CREATE INDEX IF NOT EXISTS ix_order_recommendations_category 
    ON order_recommendations(category);
CREATE INDEX IF NOT EXISTS ix_order_recommendations_profile 
    ON order_recommendations(species, breed, age_range, category);

-- Create pet_preferences table
-- Tracks items ordered by users for personalization
CREATE TABLE IF NOT EXISTS pet_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pet_id UUID NOT NULL REFERENCES pets(id) ON DELETE CASCADE,
    category VARCHAR(30) NOT NULL,
    preference_type VARCHAR(20) NOT NULL DEFAULT 'custom',
    item_name VARCHAR(500) NOT NULL,
    used_count INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes for preferences lookup
CREATE INDEX IF NOT EXISTS ix_pet_preferences_pet_category 
    ON pet_preferences(pet_id, category);
CREATE INDEX IF NOT EXISTS ix_pet_preferences_preference_type 
    ON pet_preferences(preference_type);

-- Add new order_state values to user table comment (informational only)
-- States: awaiting_order_category, awaiting_recommendation_selection,
--         awaiting_order_items, awaiting_order_pet, awaiting_order_confirm

COMMENT ON TABLE order_recommendations IS 
    'Caches AI-generated recommendations for pet profiles to reduce API calls';
COMMENT ON TABLE pet_preferences IS 
    'Tracks items ordered by users to understand preferences and personalize recommendations';
