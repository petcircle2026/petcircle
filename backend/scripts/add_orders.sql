-- PetCircle — Add Orders table and user order flow columns
-- Run this migration against the Supabase PostgreSQL database.

-- 1. Create orders table
CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    pet_id UUID REFERENCES pets(id) ON DELETE SET NULL,
    category VARCHAR(30) NOT NULL,
    items_description VARCHAR(2000) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    admin_notes VARCHAR(2000),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 2. Create indexes for common query patterns
CREATE INDEX IF NOT EXISTS ix_orders_user_id ON orders(user_id);
CREATE INDEX IF NOT EXISTS ix_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS ix_orders_created_at ON orders(created_at);

-- 3. Add order flow state columns to users table
ALTER TABLE users ADD COLUMN IF NOT EXISTS order_state VARCHAR(30);
ALTER TABLE users ADD COLUMN IF NOT EXISTS active_order_id UUID REFERENCES orders(id) ON DELETE SET NULL;
