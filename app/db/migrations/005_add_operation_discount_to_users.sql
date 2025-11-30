-- Migration: Add operation discount code fields to users table
-- Date: 2025-11-25
-- Description: Add fields to store active discount code for operations

-- For SQLite
ALTER TABLE users ADD COLUMN operation_discount_code_id INTEGER NULL;
ALTER TABLE users ADD COLUMN operation_discount_percent INTEGER NULL;

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_users_operation_discount_code_id ON users(operation_discount_code_id);

