-- Migration: Add operation details to operations table
-- Date: 2025-11-25
-- Description: Add model, prompt, and image_count fields to track operation details

-- For SQLite
ALTER TABLE operations ADD COLUMN model TEXT NULL;  -- Model used (e.g., "nano-banana-pro", "seedream")
ALTER TABLE operations ADD COLUMN prompt TEXT NULL;  -- User prompt (optional, for analytics)
ALTER TABLE operations ADD COLUMN image_count INTEGER NULL;  -- Number of images (for merge operations)

-- Create index on model for analytics
CREATE INDEX IF NOT EXISTS idx_operations_model ON operations(model);

-- Create index on type and model for better queries
CREATE INDEX IF NOT EXISTS idx_operations_type_model ON operations(type, model);





