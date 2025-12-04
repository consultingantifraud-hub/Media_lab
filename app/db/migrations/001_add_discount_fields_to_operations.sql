-- Migration: Add discount fields to operations table
-- Date: 2025-11-24
-- Description: Add original_price and discount_percent fields to track discounts in operations

-- For SQLite
ALTER TABLE operations ADD COLUMN original_price INTEGER NULL;
ALTER TABLE operations ADD COLUMN discount_percent INTEGER NULL;

-- For PostgreSQL (if using PostgreSQL, uncomment and use this instead):
-- ALTER TABLE operations ADD COLUMN IF NOT EXISTS original_price INTEGER NULL;
-- ALTER TABLE operations ADD COLUMN IF NOT EXISTS discount_percent INTEGER NULL;

-- Add comments (PostgreSQL only):
-- COMMENT ON COLUMN operations.original_price IS 'Original price before discount (if discount was applied)';
-- COMMENT ON COLUMN operations.discount_percent IS 'Discount percentage applied (10, 20, 30, etc.)';









