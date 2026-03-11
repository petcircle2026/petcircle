"""
PetCircle — Database Migration Script for Order Recommendations

Applies the database schema changes for order recommendations and pet preferences.

Usage:
    python -m scripts.migrate_orders_recommendations

This script:
1. Creates order_recommendations table
2. Creates pet_preferences table
3. Creates necessary indexes
4. Adds comments to tables

To run:
    cd backend
    python scripts/migrate_orders_recommendations.py
"""

import logging
from sqlalchemy import text
from app.database import engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate():
    """Apply database migration for order recommendations and pet preferences."""
    migration_sql = """
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
    """

    try:
        with engine.begin() as connection:
            for statement in migration_sql.split(';'):
                statement = statement.strip()
                if statement:
                    logger.info(f"Executing: {statement[:50]}...")
                    connection.execute(text(statement))
        
        logger.info("✓ Migration completed successfully")
        return True
    
    except Exception as e:
        logger.error(f"✗ Migration failed: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    success = migrate()
    exit(0 if success else 1)
