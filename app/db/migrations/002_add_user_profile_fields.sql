-- Migration: Add user profile fields to users table
-- Date: 2025-11-25
-- Description: Add Telegram user profile information (username, first_name, last_name, language_code, is_premium, last_activity_at)

-- For SQLite
ALTER TABLE users ADD COLUMN username TEXT NULL;
ALTER TABLE users ADD COLUMN first_name TEXT NULL;
ALTER TABLE users ADD COLUMN last_name TEXT NULL;
ALTER TABLE users ADD COLUMN language_code TEXT NULL;
ALTER TABLE users ADD COLUMN is_premium INTEGER DEFAULT 0;  -- SQLite uses INTEGER for boolean (0/1)
ALTER TABLE users ADD COLUMN last_activity_at DATETIME NULL;

-- Create index on username for faster lookups
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

-- Create index on last_activity_at for analytics
CREATE INDEX IF NOT EXISTS idx_users_last_activity ON users(last_activity_at);

