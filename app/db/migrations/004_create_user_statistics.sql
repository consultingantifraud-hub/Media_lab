-- Migration: Create user_statistics table
-- Date: 2025-11-25
-- Description: Create table for aggregated user statistics

-- For SQLite
CREATE TABLE IF NOT EXISTS user_statistics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    total_operations INTEGER DEFAULT 0,
    total_spent INTEGER DEFAULT 0,  -- Total spent in rubles
    operations_by_type TEXT NULL,  -- JSON: {"generate": 10, "merge": 5, ...}
    models_used TEXT NULL,  -- JSON: {"nano-banana-pro": 3, "seedream": 2, ...}
    first_operation_at DATETIME NULL,
    last_operation_at DATETIME NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_user_statistics_user_id ON user_statistics(user_id);
CREATE INDEX IF NOT EXISTS idx_user_statistics_total_spent ON user_statistics(total_spent);
CREATE INDEX IF NOT EXISTS idx_user_statistics_last_operation ON user_statistics(last_operation_at);

